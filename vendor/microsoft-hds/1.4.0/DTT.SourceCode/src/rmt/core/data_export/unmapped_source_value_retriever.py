from pyspark.sql import DataFrame
from pyspark.sql.functions import lit

from rmt.core.data_management.contributor import ContributorType
from rmt.core.values_mapping.mapping_schema import MappingSchema

MISSING_TARGET_VALUE = -1


class UnmappedSourceValuesRetriever:
    @staticmethod
    def retrieve_unmapped_source_values(source_distinct_values_df: DataFrame, mapping_df: DataFrame) -> DataFrame:
        unmapped_values_df = (
            source_distinct_values_df.join(
                mapping_df,
                on=[MappingSchema.MAPPING_FIELD_NAME_SOURCE_VALUE, MappingSchema.MAPPING_FIELD_NAME_TARGET_FIELD, MappingSchema.MAPPING_FIELD_NAME_TARGET_TABLE],
                how="left_anti",
            )
            .withColumn(MappingSchema.MAPPING_FIELD_NAME_TARGET_VALUE, lit(MISSING_TARGET_VALUE))
            .withColumn(MappingSchema.MAPPING_FIELD_NAME_SOURCE_DOMAIN, lit(ContributorType.Customer.name))
        )

        return unmapped_values_df
