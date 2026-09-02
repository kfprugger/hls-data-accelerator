from typing import FrozenSet, List

from common.model.source_to_reference_mapping import SourceToReferenceMapping
from pyspark.sql import DataFrame, SparkSession

from common.utils.logging import Logger
from dmf.model.reference_values_configuration import ReferenceValuesConfiguration
from dmf.reference_values.reference_values_mapping_reader import (
    ReferenceValuesMappingReader,
)
from dmf.reference_values.reference_values_mapping_schema import (
    ReferenceValuesMappingSchema,
)
from dmf.utils.dataframe_utils import DataFrameUtils
from dmf.utils.global_constants import GlobalConstants


class ReferenceValuesEnricher:
    def __init__(
        self,
        reference_mapping_df: DataFrame,
        reference_values_configuration: ReferenceValuesConfiguration,
    ):
        self.reference_values_configuration = reference_values_configuration
        if reference_mapping_df is None:
            self.reference_mapping_df = None
        else:
            self.reference_mapping_df = reference_mapping_df.where(
                f"{ReferenceValuesMappingSchema.MAPPING_FIELD_NAME_SOURCE_DOMAIN} = "
                f"'{self.reference_values_configuration.source_domain}'"
            )
        self.reference_mapping_df_by_target_table_and_field = {}

    def _get_filtered(self, target_table: str, target_field: str) -> DataFrame:
        # get the mapping for the target table and field from cache or create it
        key: str = f"{target_table}{target_field}"
        if key not in self.reference_mapping_df_by_target_table_and_field:
            self.reference_mapping_df_by_target_table_and_field[key] = (
                self.reference_mapping_df.where(
                    f"{ReferenceValuesMappingSchema.MAPPING_FIELD_NAME_TARGET_TABLE} ="
                    f" '{target_table}' and {ReferenceValuesMappingSchema.MAPPING_FIELD_NAME_TARGET_FIELD} = '{target_field}'"
                )
            )
            self.reference_mapping_df_by_target_table_and_field[key].cache()
        return self.reference_mapping_df_by_target_table_and_field[key]

    def enrich(
        self,
        source_df: DataFrame,
        source_to_reference_mappings: FrozenSet[SourceToReferenceMapping],
        replace_values_in_src_column: bool = True,
    ) -> DataFrame:
        source_fields = []
        for source_to_reference_mapping in source_to_reference_mappings:
            if source_to_reference_mapping.source_field_name in source_df.columns:
                source_fields.append(source_to_reference_mapping.source_field_name)
                filtered_mapping_df = self._get_filtered(
                    source_to_reference_mapping.target_reference_table_name,
                    source_to_reference_mapping.target_reference_field_name,
                )
                joined_df = source_df.join(
                    filtered_mapping_df,
                    on=source_df[source_to_reference_mapping.source_field_name].cast(
                        "string"
                    )
                    == filtered_mapping_df[
                        ReferenceValuesMappingSchema.MAPPING_FIELD_NAME_SOURCE_VALUE
                    ],
                    how="leftouter",
                )
                source_df = joined_df.drop(
                    ReferenceValuesMappingSchema.MAPPING_FIELD_NAME_SOURCE_VALUE,
                    ReferenceValuesMappingSchema.MAPPING_FIELD_NAME_SOURCE_DOMAIN,
                    ReferenceValuesMappingSchema.MAPPING_FIELD_NAME_TARGET_TABLE,
                    ReferenceValuesMappingSchema.MAPPING_FIELD_NAME_TARGET_FIELD,
                )
                if not replace_values_in_src_column:
                    source_fields.remove(source_to_reference_mapping.source_field_name)
                    source_fields.append(source_to_reference_mapping.mapped_column_name)
                    required_mapped_column_name = (
                        source_to_reference_mapping.mapped_column_name
                    )
                else:
                    source_df = source_df.drop(
                        source_to_reference_mapping.source_field_name
                    )
                    required_mapped_column_name = (
                        source_to_reference_mapping.source_field_name
                    )
                source_df = DataFrameUtils.with_column_renamed_fast(
                    source_df,
                    ReferenceValuesMappingSchema.MAPPING_FIELD_NAME_TARGET_VALUE,
                    required_mapped_column_name,
                )
                Logger.debug(
                    f"Reference column enriched: {source_to_reference_mapping.source_field_name} with "
                    f"{source_to_reference_mapping.target_reference_table_name}.{source_to_reference_mapping.target_reference_field_name}"
                )
            else:
                msg = (
                    f"Reference values enriching. Source field: '{source_to_reference_mapping.source_field_name}' "
                    f"was not found in the source dataframe: '{source_df.columns}'"
                )
                raise Exception(msg)
            source_df = self.handle_unmatched_values(source_df, source_fields)
        Logger.debug(
            f"Reference values enriching end. Source fields: {str(source_fields)}"
        )
        return source_df

    def handle_unmatched_values(
        self, source_df: DataFrame, source_fields: List[str]
    ) -> DataFrame:
        adapter_name = source_df.sparkSession.conf.get(
            GlobalConstants.SPARK_CONFIG_ADAPTER_NAME_VARIABLE, None
        )
        dtt_start_execution_time = source_df.sparkSession.conf.get(
            GlobalConstants.SPARK_CONFIG_DTT_START_EXECUTION_TIMESTAMP, None
        )
        if self.reference_values_configuration.fail_upon_missing_reference_values:
            Logger.debug(
                "'fail_upon_missing_reference_values' is true, checking for unmatched values."
            )
            where_str = " is NULL or ".join(source_fields) + " is NULL"
            null_df = source_df.where(where_str)
            if DataFrameUtils.is_not_empty(null_df):
                msg = (
                    "Reference values enriching. Source values where not found in the mapping table. "
                    "Failing due to setting in adapter: failUponMissingReferenceValues = true"
                )
                missing_reference_value_msg = "DTT has stopped execution."
                self._log_missing_reference_value(
                    missing_reference_value_msg, adapter_name, dtt_start_execution_time
                )
                raise Exception(msg)

        else:
            Logger.debug(
                f"Reference filling with default value {self.reference_values_configuration.default_value}."
            )
            if self.reference_values_configuration.default_value is not None:
                missing_reference_value_msg = "DTT continues the execution. A default value is used to populate the target reference value."
                self._log_missing_reference_value(
                    missing_reference_value_msg, adapter_name, dtt_start_execution_time
                )
                source_df = source_df.fillna(
                    self.reference_values_configuration.default_value, source_fields
                )
        return source_df

    def _log_missing_reference_value(
        self, msg: str, adapter_name: str | None, dtt_start_execution_time: str | None
    ):
        if adapter_name and dtt_start_execution_time:
            Logger.error(
                f"At least one source reference value isn't mapped to a target reference value. {msg}.\
                         DTT execution has started at: {dtt_start_execution_time}.\
                         DTT adapter name is: {adapter_name},\
                         adapter source domain is: {self.reference_values_configuration.source_domain}.\
                         Please refer to the documentation, to learn how Reference Data Management can help fix the issue",
                extra={
                    "dtt_start_execution_timestamp": dtt_start_execution_time,
                    "adapter_source_domain": self.reference_values_configuration.source_domain,
                    "dtt_adapter_name": adapter_name,
                },
            )

    @staticmethod
    def create_from_mapping_file(
        spark: SparkSession,
        reference_values_configuration: ReferenceValuesConfiguration,
    ) -> "ReferenceValuesEnricher":
        reference_values_mapping_df = ReferenceValuesMappingReader.read(
            spark, reference_values_configuration
        )
        if reference_values_mapping_df is None:
            if reference_values_configuration.default_value is None:
                msg = "Reference values mapping table could not be loaded and no default value was defined in adapter"
                raise Exception(msg)
            else:
                reference_values_mapping_df = spark.createDataFrame(
                    [], ReferenceValuesMappingSchema.SCHEMA
                )
        return ReferenceValuesEnricher(
            reference_values_mapping_df, reference_values_configuration
        )
