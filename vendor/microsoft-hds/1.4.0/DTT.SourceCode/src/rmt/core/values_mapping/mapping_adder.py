from pyspark.sql import DataFrame

from rmt.core.values_mapping.mapping_schema import MappingSchema


class MappingAdder:

    @staticmethod
    def add(mapping_df: DataFrame, mapping_definition_df: DataFrame) -> DataFrame:
        result_df = mapping_df.unionByName(mapping_definition_df)
        return result_df

    @staticmethod
    def add_source(mapping_df: DataFrame, mapping_source_df) -> DataFrame:
        mapping_df_without_source_mappings = mapping_df.join(
            mapping_source_df,
            on=[
                MappingSchema.MAPPING_FIELD_NAME_SOURCE_DOMAIN,
                MappingSchema.MAPPING_FIELD_NAME_SOURCE_VALUE,
                MappingSchema.MAPPING_FIELD_NAME_TARGET_TABLE,
                MappingSchema.MAPPING_FIELD_NAME_TARGET_FIELD,
            ],
            how="left_anti",
        )

        result_df = mapping_df_without_source_mappings.unionByName(mapping_source_df)
        return result_df
