import os
from typing import Dict, List

from common.reader.reader import Reader
from common.reader.reader_factory import ReaderFactory
from delta import DeltaTable

from common.model.data_access_definition import DataAccessDefinition, DataSourceId
from dmf.model.source_configuration import MappingDefinition, SourceConfiguration, SourceTableSchema
from dmf.model.target_configuration.target_configuration import TargetConfiguration
from dmf.last_processed_line_computer.last_processed_lines import LastProcessedLineCalculator
from common.utils.logging import Logger
from dmf.reference_values.reference_values_enricher import ReferenceValuesEnricher
from dmf.transformations.model.transformation_types import Source2TargetIdMapping
from dmf.transformations.processor.base_processor import BaseProcessor
from dmf.transformations.processor.column_expression_builder import ColumnExpressionBuilder
from dmf.transformations.processor.conditions.condition_source_columns_applier import ConditionedSourceColumnsApplier
from dmf.transformations.processor.conditions.id_mapping import ConditionedIdMappingAdjuster
from dmf.transformations.processor.field_values_source_enricher import FieldValuesSourceEnricher
from dmf.transformations.processor.target_processor import TargetProcessor
from dmf.transformations.utils.min_date_filter import MinDateFilter
from dmf.utils.global_constants import GlobalConstants
from dmf.utils.logging_utils import SyntheticId, Timed
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.utils import AnalysisException
from pyspark.sql import functions as F

from dmf.transformations.processor.column_selector import ColumnSelector
from dmf.model.internal.target_table_schema_helper import TargetTableSchemaHelper


@SyntheticId
class SourceProcessor(BaseProcessor):
    DEFAULT_SOURCE_DATA_PARTITIONS = 100

    def __init__(
            self,
            spark: SparkSession,
            config: SourceConfiguration,
            reference_values_enricher: ReferenceValuesEnricher
    ):
        self._spark: SparkSession = spark
        self.config: SourceConfiguration = config
        if self.config.table_schema is None:
            raise ValueError(f"got config without source schema {self.config}")
        self.df: DataFrame = None
        self._id_mapping_definitions: Dict[DataSourceId, DataAccessDefinition]
        self._reference_values_enricher = reference_values_enricher
        self._schema: SourceTableSchema = self.config.table_schema
        if self._schema is None:
            raise ValueError(f"got config without source schema {self.config}")
        self.is_empty: bool = False
        self.source_id = config.source_id
        self._preprocessed_data_location = None
        self._preprocessed_data_format = "delta"
        try:
            self._data_partitions = int(spark.conf.get(GlobalConstants.SPARK_CONFIG_DTT_DMF_SOURCE_DATA_PARTITIONS))
        except Exception as e:
            Logger.warn(f"Unable to parse {GlobalConstants.SPARK_CONFIG_DTT_DMF_SOURCE_DATA_PARTITIONS}. {e}")
            self._data_partitions = None
        self._data_partitions = self._data_partitions or self.DEFAULT_SOURCE_DATA_PARTITIONS
        Logger.info(f"{self} created with data partitions: {self._data_partitions}")

    def __str__(self):
        return f"source {self.source_id}"

    def __repr__(self) -> str:
        return f"SourceProcessor[{self.id}][{self.source_id:.30}]"

    @property
    def id_mapping_definitions(self):
        return self._id_mapping_definitions

    @id_mapping_definitions.setter
    def id_mapping_definitions(self, id_mapping_definitions: Dict[DataSourceId, DataAccessDefinition]):
        self._id_mapping_definitions = id_mapping_definitions

    def _preprocess(self) -> None:
        # calculate min date (unrelated to source data! merely the target data)
        min_date = LastProcessedLineCalculator(self._spark).compute_last_processed_line_in_source_table(
            executor=None, source_config=self.config
        )
        # filter source by date
        Logger.debug(f"{self} filtering by min_date: {min_date}")
        self.df = MinDateFilter.filter(
            df=self.df,
            min_date=min_date,
            date_col_name=self._schema.source_modified_date_column_name,
        )

        self.df = ColumnExpressionBuilder.build_column_expressions(self.df, self._schema.columns)
        self.df, extra_literal_columns = FieldValuesSourceEnricher.enrich(self.config, self.df)
        self.df = self._reference_values_enricher.enrich(self.df, self.config.source_to_reference_mappings)
        self.df, extra_conditioned_columns = ConditionedSourceColumnsApplier(
            self._spark,
            self.config,
            self.df,
            self._reference_values_enricher.reference_values_configuration.default_value,
        ).apply()
        try:
            self.df = ColumnSelector.select_specific_columns(
                self.df,
                list(self._schema.columns) + extra_literal_columns + extra_conditioned_columns,
            )
        except AnalysisException as ae:
            if "ambiguous" in str(ae):
                raise Exception(
                    "Multiple fields with same name were found. Use a unique aliases for these fields in the query to resolve the ambigiuity."
                ) from ae
            else:
                raise

    @Timed(Logger)
    def read(self) -> int:
        if not self._read_inner():
            self.is_empty = True
        else:
            self._preprocess()
            self._save_data()
        return self.is_empty

    def _save_data(self):
        self._preprocessed_data_location = os.path.join(self.config.secondary_lake_location,
                                                        "PREPROCESSED_SOURCE_DATA",
                                                        self.config.feed_id,
                                                        self.source_id)
        try:
            delta_table = DeltaTable.forPath(self._spark, self._preprocessed_data_location)
            delta_table.vacuum()
        except Exception as e:
            Logger.warn(f"Failed to vacuum delta table from location: {self._preprocessed_data_location}. {e}")

        self.df.write.format(self._preprocessed_data_format).mode("overwrite").save(self._preprocessed_data_location)
        self.df = self._spark.read.format(self._preprocessed_data_format).load(self._preprocessed_data_location) \
            .repartition(self._data_partitions)
        self.is_empty = self.df.isEmpty()

    def _read_inner(self) -> bool:
        Logger.info(f"{self} reading source table: '{self.config.data_access_definition}'")
        reader: Reader = ReaderFactory.get_instance(self.config.data_access_definition)
        source_df = reader.read(self._spark)
        if source_df is not None:
            self.df = source_df.repartition(self._data_partitions)

        return reader.validate(df=self.df, data_access_definition=self.config.data_access_definition)

    def process(self) -> List[TargetProcessor]:
        if self.is_empty:
            return []

        if not self.id_mapping_definitions:
            Logger.info(f"{self} no id mapping definitions")

        target_processors = []
        for target_config in self.config.target_configurations:
            target_processor = self._create_target_processor(target_config)
            target_processors.append(target_processor)

        Logger.info(f"{self} process end. returning target processors: {[tp.id for tp in target_processors]}")
        return target_processors

    def _create_target_processor(self, target_config):
        target_id_mappings: List[Source2TargetIdMapping] = self._calc_id_mappings(target_config)
        target_id_mappings, source_ids_with_conditions = ConditionedIdMappingAdjuster.adjust(
            target_config, target_id_mappings
        )
        mapping_table_data_access_definitions: Dict[DataSourceId, DataAccessDefinition] = {}
        for target_id_mapping in target_id_mappings:
            mapping_table_data_access_definitions[
                target_id_mapping.id_mapping_df_name
            ] = self._find_mapping_table_data_access_definitions(target_id_mapping.id_mapping_df_name)

        target_processor = TargetProcessor(
            spark=self._spark,
            target_config=target_config,
            source_schema=self._schema,
            source_df=self.df,
            id_mappings=target_id_mappings,
            source_ids_with_conditions=source_ids_with_conditions,
            id_mapping_table_access_definitions=mapping_table_data_access_definitions,
            parent_id=self.source_id,
        )

        return target_processor

    def _find_mapping_table_data_access_definitions(self, id_mapping_df_name: str) -> DataAccessDefinition:
        for mapping_definition in self.id_mapping_definitions.values():
            if mapping_definition.data_source_id == id_mapping_df_name:
                return mapping_definition

        raise ValueError(f"Adapter mapping definition for table '{id_mapping_df_name}' was not defined")

    def _calc_id_mappings(self, target_config: TargetConfiguration) -> List[Source2TargetIdMapping]:
        src_to_target_id_mappings = []
        already_appended_target_id_column_names = []
        for mapping_definition in self.config.mapping_definitions:
            append = False
            if mapping_definition.target_mapping_table_name == target_config.target_id:
                append = True

            if not append:
                relations_to_mapping_table = TargetTableSchemaHelper.get_relations_pointing_to_table(
                    target_config.table_schema,
                    mapping_definition.target_mapping_table_name,
                )
                has_fk_to_mapping_definition = bool(relations_to_mapping_table)
                if has_fk_to_mapping_definition:
                    append = True

            if append and mapping_definition.target_id_column_name not in already_appended_target_id_column_names:
                src_to_target_id_mappings.append(
                    Source2TargetIdMapping(
                        id_mapping_df_name=self.id_mapping_definitions[
                            mapping_definition.target_mapping_table_name
                        ].data_source_id,
                        source_id_col_name=SourceProcessor._calc_source_id_column_name(mapping_definition),
                        target_id_col_name=mapping_definition.target_id_column_name,
                    )
                )
                already_appended_target_id_column_names.append(mapping_definition.target_id_column_name)
        return src_to_target_id_mappings

    @staticmethod
    def _calc_source_id_column_name(mapping_definition: MappingDefinition) -> str:
        return SourceProcessor.calc_source_id_column_name(mapping_definition.external_id_column_name,
                                                          mapping_definition.internal_id_column_name)

    @staticmethod
    def calc_source_id_column_name(external_id_column_name: str, internal_id_column_name: str) -> str:
        return external_id_column_name or internal_id_column_name

    def validate(self) -> bool:
        self.read()
        if self.is_empty:
            return True
        validation_methods = [
            self._validate_modified_on_column(),
        ]
        validation_status = all(validation_methods)
        return validation_status

    def _validate_modified_on_column(self) -> bool:
        status = self.df.where(F.col(self._schema.source_modified_date_column_name).isNull()).isEmpty()
        if not status:
            Logger.error(f"{self} has NULL values in modified_on column")

        return status
