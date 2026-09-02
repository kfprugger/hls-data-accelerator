from typing import Dict, FrozenSet, List

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.types import StructType

from common.model.data_access_definition import DataAccessDefinition, DataSourceId
from dmf.model.source_configuration import SourceTableSchema, TargetConfiguration
from dmf.model.target_configuration.target_table_schema import TableColumn
from common.utils.logging import Logger
from dmf.transformations.model.transformation_metadata_factory import TransformationMetaDataFactory
from dmf.transformations.model.transformation_types import PartitionConfig, Source2TargetIdMapping, TransformationData, \
    TransformationMetaData
from dmf.transformations.processor.etl_processor import ETLProcessor
from common.reader.reader import Reader
from common.reader.reader_factory import ReaderFactory
from dmf.transformations.transformer.transformer import Transformer
from dmf.transformations.transformer.transformer_factory import TransformerFactory
from dmf.transformations.writer.writer_factory import WriterFactory
from dmf.utils.dataframe_utils import DataFrameUtils


class TargetProcessor(ETLProcessor):
    def __init__(self,
                 spark: SparkSession,
                 target_config: TargetConfiguration,
                 source_schema: SourceTableSchema,
                 source_df: DataFrame,
                 id_mappings: List[Source2TargetIdMapping],
                 source_ids_with_conditions: List[str],
                 id_mapping_table_access_definitions: Dict[DataSourceId, DataAccessDefinition],
                 parent_id: str = ""):

        super().__init__(spark)
        self._target_config = target_config
        self._source_schema = source_schema
        self._source_df: DataFrame = source_df
        self._id_mappings: List[Source2TargetIdMapping] = id_mappings
        self._source_ids_with_conditions = source_ids_with_conditions
        self._id_mapping_table_access_definitions: Dict[
            DataSourceId, DataAccessDefinition] = id_mapping_table_access_definitions
        self._target_df: DataFrame
        self._mapping_dfs: Dict[DataSourceId, DataFrame] = {}
        self._target_partitions = self._transformation_partition_configs()
        self.target_id = target_config.target_id
        self.parent_id = parent_id
        self.transformation_metadata: TransformationMetaData = None

    def __str__(self) -> str:
        return f"TargetProcessor[{self.target_id}, parent={self.parent_id}]"

    def __repr__(self) -> str:
        return f"TargetProcessor[{self.id}][{self.target_id}]({self._target_config})"

    def read(self):
        reader: Reader = ReaderFactory.get_instance(self._target_config.data_access_definition)
        self._target_df = reader.read(self.spark)
        if not self._target_df:
            Logger.info(f"{self}. Target does not exist")
            self._target_df = self._empty_target_df(self._target_config.table_schema.columns)
        else:
            Logger.info(f"{self}. Target exists")

        for id_mapping_table_name, id_mapping_table_access_definition in self._id_mapping_table_access_definitions.items():
            mapping_table_reader: Reader = ReaderFactory.get_instance(id_mapping_table_access_definition)
            mapping_table_df = mapping_table_reader.read(self.spark)
            if not mapping_table_df:
                raise LookupError(f"IDs mapping table does not exist: '{id_mapping_table_name}'")
            self._mapping_dfs[id_mapping_table_name] = mapping_table_df

    def _empty_target_df(self, columns: FrozenSet[TableColumn]):
        schema = StructType()
        for column in columns:
            schema.add(column.name, column.type, False)
        return DataFrameUtils.create_empty_df(self.spark, schema)

    def _transform(self, df: DataFrame) -> DataFrame:
        transformer: Transformer = TransformerFactory.get_instance(self._target_config, str(self))
        transformer_data = TransformationData(self._source_df, self._target_df, self._mapping_dfs)
        self.transformation_metadata: TransformationMetaData = self._create_transformation_metadata()
        try:
            transformed_df = transformer.transform(transformer_data, self.transformation_metadata)
        except Exception as e:
            Logger.error(f"Error while transforming data to table {self.target_id}. "
                         f"Context: {self}: {e}")
            raise

        return transformed_df

    def _write(self, df: DataFrame):
        writer = WriterFactory.get_instance(self._target_config.data_access_definition, self.id, df.sparkSession, self.transformation_metadata)
        partition_column = self._target_partitions[0].partition_col_name if self._target_partitions and len(
            self._target_partitions) > 0 else None
        try:
            writer.write(df, partition_column=partition_column)
        except Exception as e:
            Logger.error(f"Error while writing data to table {self.target_id}. "
                         f"Context: {self}: {e}")
            raise

    def _transformation_partition_configs(self) -> List[PartitionConfig]:
        transformation_partition_configs = []
        for config_partition_config in self._target_config.partitions_config:
            transformation_partition_config = PartitionConfig(
                input_col_name=config_partition_config.input_col_name,
                partition_col_name=config_partition_config.partition_col_name,
                partition_col_type=config_partition_config.partition_col_type,
                input_col_to_partition_col_rule=config_partition_config.input_col_to_partition_col_rule
            )
            transformation_partition_configs.append(transformation_partition_config)

        return transformation_partition_configs

    def _create_transformation_metadata(self) -> TransformationMetaData:
        metadata = TransformationMetaDataFactory(
            source_schema=self._source_schema,
            target_config=self._target_config,
            source_partitions_configs=self._target_partitions,
            source_to_target_ids_mapping=self._id_mappings,
            source_ids_with_conditions=self._source_ids_with_conditions,
        ).create()
        return metadata
