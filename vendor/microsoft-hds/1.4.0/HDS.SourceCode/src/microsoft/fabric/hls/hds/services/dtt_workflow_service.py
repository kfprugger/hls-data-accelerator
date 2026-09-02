import typing_extensions
from pyspark.sql import SparkSession
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants
from microsoft.fabric.hls.hds.global_constants.logging_constants import (
    LoggingConstants as LC,
)
from configuration_compiler.api import persist_rmt_spec
from configuration_compiler.api import persist_dtt_spec
from microsoft.fabric.hls.hds.utils.extension_parser import ExtensionParser
from importlib import reload
import typing_extensions
from rmt.runners.fabric_runner import FabricRunner as FabricRunner_RMT
from dmf.runners.fabric.fabric_runner import FabricRunner as FabricRunner_DMF
from microsoft.fabric.hls.hds.utils.logging_helper import LoggingHelper
from pyspark.sql import SparkSession
from microsoft.fabric.hls.hds.utils.extension_parser import ExtensionParser
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import (
    MSSparkUtilsClientBase,
)
from microsoft.fabric.hls.hds.utils.utils import Utils
from microsoft.fabric.hls.hds.utils.dtt_json_config_cleaner import JsonConfigCleaner


class DTTWorkflowService:
    def __init__(
        self,
        spark: SparkSession,
        rmt_out_path: str,
        dtt_out_path: str,
        config_files: dict = None,
        rmt_ordered_mapping_definitions_folders: list[str] = [],
        rmt_reference_tables_folders_paths: list[str] = [],
        executeRMTReferenceTable: bool = False,
        mssparkutils_client: MSSparkUtilsClientBase = None,
        **kwargs,
    ):
        """
        Uses DTT library to transform and ingest data
        Args:
        - spark: spark session
        - rmt_out_path: str, where to persist the rmt spec,
        - dtt_out_path: str, where to persist the DTT spec,
        - config_files: dict, (Config files must be provided to run RMT and DMT transformation) dictionary containing the following key-value pairs:
            - 'adaptor_file_location': str, path to the adaptor configuration file.
            - 'adaptor_file_content': str, content of the adaptor configuration file.
            - 'target_db_semantics_file_location': str, path to the target DB semantics file.
            - 'target_db_semantics_file_content': str, content of the target DB semantics file.
            - 'env_config_file_location': str, path to the environment config file.
            - 'env_config_file_content': str, content of the environment config file.
            - 'target_db_schema_file_location': str, path to the target DB schema file.
            - 'target_db_schema_file_content': str, content of the target DB schema file.
            - 'db_schema_config_location': str, path to the DB schema config file.
            - 'db_schema_config_content': str, content of the DB schema config file.
            - 'target_db_semantics_config_file_location': str, path to the target DB semantics config file.
            - 'target_db_semantics_config_file_content': str, content of the target DB semantics config file.
            - 'rmt_target_path': str, path to reference data table in the target Lakehouse.
        - rmt_reference_tables_folders_paths: list[str], path to the target DB semantics reference data definitions
        - rmt_ordered_mapping_definitions_folders: list[str], path to the target DB semantics ordered mapping data definitions
        - rmt_target_path: str, path to reference data table in the target Lakehouse
        - executeRMTReferenceTable: bool, whether need to execute create_reference_data_tables method
        - mssparkutils_client: MSSparkUtilsClientBase, spark utils client
        - **kwargs (dict): An optional dictionary that customer can use to configure the dtt workflow service
            - run_id (str): The run_id for the run. If none is provided, one will be generated
        """
        self.spark = spark
        self._logger = LoggingHelper.get_omopingestion_logger(
            self.spark, self.__class__.__name__, GlobalConstants.LOGGING_LEVEL
        )
        self.mssparkutils_client = Utils.get_mssparkutils_client(mssparkutils_client)

        self.cleaner = JsonConfigCleaner(spark, self.mssparkutils_client)
        self.cleaner.clean_config_files_dict(config_files)

        ExtensionParser.register(spark)
        if config_files is None:
            self._logger.error(f"{LC.DTT_CONFIG_FILES_EMPTY_MSG}")
            raise ValueError(f"{LC.DTT_CONFIG_FILES_EMPTY_MSG}")

        # Accessing individual config files from the dictionary
        adaptor_file_location = config_files.get("adaptor_file_location", "")
        adaptor_file_content = config_files.get("adaptor_file_content", "")

        target_db_semantics_file_location = config_files.get(
            "target_db_semantics_file_location", ""
        )
        target_db_semantics_file_content = config_files.get(
            "target_db_semantics_file_content", ""
        )

        env_config_file_location = config_files.get("env_config_file_location", "")
        env_config_file_content = config_files.get("env_config_file_content", "")

        target_db_schema_file_location = config_files.get(
            "target_db_schema_file_location", ""
        )
        target_db_schema_file_content = config_files.get(
            "target_db_schema_file_content", ""
        )

        db_schema_config_location = config_files.get("db_schema_config_location", "")
        db_schema_config_content = config_files.get("db_schema_config_content", "")

        target_db_semantics_config_file_location = config_files.get(
            "target_db_semantics_config_file_location", ""
        )
        target_db_semantics_config_file_content = config_files.get(
            "target_db_semantics_config_file_content", ""
        )

        rmt_target_path = config_files.get("rmt_target_path", "")

        try:
            self.rmt_out_path = rmt_out_path
            self.dtt_out_path = dtt_out_path
            self.adaptor_file_location = adaptor_file_location
            self.target_db_semantics_file_location = target_db_semantics_file_location
            self.env_config_file_location = env_config_file_location
            self.target_db_schema_file_location = target_db_schema_file_location
            self.db_schema_config_location = db_schema_config_location
            self.adaptor_file_content = adaptor_file_content
            self.target_db_semantics_file_content = target_db_semantics_file_content
            self.target_db_schema_file_content = target_db_schema_file_content
            self.db_schema_config_content = db_schema_config_content
            self.env_config_file_content = env_config_file_content
            self.target_db_semantics_config_file_location = (
                target_db_semantics_config_file_location
            )
            self.target_db_semantics_config_file_content = (
                target_db_semantics_config_file_content
            )
            self.rmt_ordered_mapping_definitions_folders = (
                rmt_ordered_mapping_definitions_folders
            )
            self.executeRMTReferenceTable = executeRMTReferenceTable
            self.rmt_reference_tables_folders_paths = rmt_reference_tables_folders_paths
            self.rmt_target_path = rmt_target_path

            Utils.set_dtt_app_insights_connection_string(
                spark=self.spark,
                mssparkutils_client=self.mssparkutils_client,
                on_set_fn=lambda: self._logger.info(
                    f"{LC.DTT_APP_INSIGHTS_SET_INFO_MSG}"
                ),
            )

        except Exception as ex:
            self._logger.error(message=str(ex))
            raise

    def execute_dtt_workflow(self):
        """Invokes the dtt workflow"""

        # load typing_extensions for RMT
        reload(typing_extensions)

        # RMT CC
        persist_rmt_spec(
            spark=self.spark,
            out_path=self.rmt_out_path,
            adaptor_file_location=self.adaptor_file_location,
            target_db_semantics_file_location=self.target_db_semantics_file_location,
            env_config_file_location=self.env_config_file_location,
            target_db_schema_file_location=self.target_db_schema_file_location,
            db_schema_config_location=self.db_schema_config_location,
            adaptor_file_content=self.adaptor_file_content,
            target_db_semantics_file_content=self.target_db_semantics_file_content,
            target_db_schema_file_content=self.target_db_schema_file_content,
            db_schema_config_content=self.db_schema_config_content,
            env_config_file_content=self.env_config_file_content,
        )

        # DMF CC
        persist_dtt_spec(
            spark=self.spark,
            out_path=self.dtt_out_path,
            dmf_adaptor_file_location=self.adaptor_file_location,
            target_db_semantics_file_location=self.target_db_semantics_file_location,
            target_db_semantics_config_file_location=self.target_db_semantics_config_file_location,
            target_db_schema_file_location=self.target_db_schema_file_location,
            db_schema_config_location=self.db_schema_config_location,
            env_config_file_location=self.env_config_file_location,
            adaptor_file_content=self.adaptor_file_content,
            target_db_semantics_file_content=self.target_db_semantics_file_content,
            target_db_semantics_config_file_content=self.target_db_semantics_config_file_content,
            target_db_schema_file_content=self.target_db_schema_file_content,
            db_schema_config_content=self.db_schema_config_content,
            env_config_file_content=self.env_config_file_content,
        )

        if self.rmt_ordered_mapping_definitions_folders:
            FabricRunner_RMT.create_reference_values_mapping(
                spark=self.spark,
                rmt_spec_path=self.rmt_out_path,
                ordered_mapping_definitions_folders=self.rmt_ordered_mapping_definitions_folders,
            )

        if self.executeRMTReferenceTable:
            FabricRunner_RMT.create_reference_data_tables(
                spark=self.spark,
                rmt_spec_path=self.rmt_out_path,
                target_path=self.rmt_target_path,
                reference_tables_folders_paths=self.rmt_reference_tables_folders_paths,
            )

        self._logger.info(f"{LC.RMT_SUCCESS_INFO_MSG}")
        FabricRunner_DMF.run(
            spark=self.spark,
            transformation_spec_path=self.dtt_out_path,
        )
        self._logger.info(f"{LC.DTT_SUCCESS_INFO_MSG}")
