import os.path
from pyspark.sql import DataFrame, SparkSession

from common.utils.logging import Logger
from dmf.model.reference_values_configuration import ReferenceValuesConfiguration
from dmf.utils.global_constants import GlobalConstants


class ReferenceValuesMappingReader:

    @staticmethod
    def read(spark: SparkSession, reference_values_configuration: ReferenceValuesConfiguration) -> DataFrame:
        try:
            path = os.path.join(reference_values_configuration.secondary_lake_location, GlobalConstants.REFERENCE_MAPPING_PATH)
            reference_mapping_df = spark.read.format("delta").load(path)
            Logger.info(f"Reference mapping file is loaded: {path}")
        except Exception as e:
            reference_mapping_df = None
            Logger.warn(f"Error on loading reference mapping from path: {path}. Original excepton: {e}")

        return reference_mapping_df
