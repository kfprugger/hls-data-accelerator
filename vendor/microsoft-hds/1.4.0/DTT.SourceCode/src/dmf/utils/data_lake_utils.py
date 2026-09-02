import os

from pyspark.sql import SparkSession

from dmf.utils.global_constants import GlobalConstants


def get_mapping_tables_location(secondary_lake_location: str) -> str:
    return os.path.join(secondary_lake_location, GlobalConstants.ID_MAPPING_PATH)


# TODO this should be removed when DMF will support only writing to delta files
def get_target_temp_location(spark: SparkSession, name: str) -> str:
    secondary_lake_root = spark.conf.get(GlobalConstants.SPARK_CONFIG_SECONDARY_LAKE_ROOT_VARIABLE)
    if not secondary_lake_root:
        raise ValueError("Secondary lake location is not defined")
    target_temp_tables_location = os.path.join(secondary_lake_root, "target_temp", name)

    return target_temp_tables_location
