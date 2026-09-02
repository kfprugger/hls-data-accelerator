import os

from pyspark.sql import SparkSession

from dmf.utils.global_constants import GlobalConstants


def get_key_mapping_location(spark: SparkSession) -> str:
    secondary_lake_root = spark.conf.get(
        GlobalConstants.SPARK_CONFIG_SECONDARY_LAKE_ROOT_VARIABLE
    )
    if not secondary_lake_root:
                raise ValueError("The of table ID mappings and reference data mappings (the 'secondary lake') should be defined in the environment file")
    id_mapping_tables_location = os.path.join(secondary_lake_root, "key_mapping")

    return id_mapping_tables_location


def get_target_temp_location(spark: SparkSession, name: str) -> str:
    secondary_lake_root = spark.conf.get(
        GlobalConstants.SPARK_CONFIG_SECONDARY_LAKE_ROOT_VARIABLE
    )
    if not secondary_lake_root:
                raise ValueError("The of table ID mappings and reference data mappings (the 'secondary lake') should be defined in the environment file")
    target_temp_tables_location = os.path.join(secondary_lake_root, "target_temp", name)

    return target_temp_tables_location
