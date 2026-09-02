import sys
import traceback

from pyspark.sql import SparkSession

from common.utils.logging import Logger
from dmf.runners.utils import RuntimeUtilities
from dmf.workflow.dmf_application import DMFApplication


class FabricRunner:

    @staticmethod
    def run(spark: SparkSession, transformation_spec_path: str):
        """
        This method is used as an entry point to DMF when executed from Synapse notebook.
        :param spark: The Spark session
        :param transformation_spec_path: The path to transformation spec file.
        After reading the transformation spec file, the method will execute DMF.
        """

        # The first thing to do is to initialize the Logger
        Logger.init_logger()

        if not RuntimeUtilities.is_runtime_environment():
            Logger.error("FabricRunner should be executed from Fabric only")
            sys.exit(0)

        # Get content of the configuration files
        try:
            transformation_spec_content = FabricRunner._read_configuration_files(spark, transformation_spec_path)

            DMFApplication.start_with_transformation_spec_content(
                spark=spark,
                transformation_spec_content=transformation_spec_content
            )
        except Exception:
            Logger.error(traceback.format_exc())

    @staticmethod
    def _read_configuration_files(spark: SparkSession, transformation_spec_path: str) -> str:
        """
        This method validates the configuration files.
        :param transformation_spec_path: The path to transformation spec file.
        If some file/s not found, the error os raised.
        """
        Logger.info(f"Reading transformation spec file {transformation_spec_path}")

        try:
            file_content = spark.sparkContext.wholeTextFiles(transformation_spec_path).collect()[0][1]
        except Exception as e:
            raise FileNotFoundError(f"Transformation Spec file {transformation_spec_path} not found", e)

        Logger.info("Transformation Spec has been read successfully")

        return file_content
