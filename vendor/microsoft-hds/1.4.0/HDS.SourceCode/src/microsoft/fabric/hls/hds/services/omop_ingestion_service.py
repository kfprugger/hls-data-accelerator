# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
import traceback
from typing import Dict
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, row_number
from pyspark.sql.window import Window
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.global_constants.logging_constants import (
    LoggingConstants as LC,
)
from microsoft.fabric.hls.hds.services.dtt_workflow_service import DTTWorkflowService
from microsoft.fabric.hls.hds.services.vocabulary_ingestion_service import (
    VocabularyIngestionService,
)
from microsoft.fabric.hls.hds.utils.utils import FolderPath, Utils
from microsoft.fabric.hls.hds.utils.extension_parser import ExtensionParser
from microsoft.fabric.hls.hds.services.dtt_workflow_service import (
    DTTWorkflowService,
)
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase
from microsoft.fabric.hls.hds.services.base_runnable_service import BaseRunnableService
from microsoft.fabric.hls.hds.data_models.execution_metadata import ExecutionMetadata, ExecutionDataType

class OMOPIngestionService(BaseRunnableService):
    def __init__(
        self,
        spark: SparkSession,
        workspace_name: str,
        solution_name: str,
        admin_lakehouse_name: str,
        inline_params: dict = None,
        one_lake_endpoint: str = GC.DEFAULT_ONE_LAKE_ENDPOINT,
        mssparkutils_client: MSSparkUtilsClientBase = None
    ):
        """
        Uses DTT library to transform and ingest data into OMOP(Gold tables)
        Args:
        - spark: spark session
        - workspace_name - str: Name of the Fabric Workspace
        - solution_name: Name of the DMH OneLake workload solution
        - admin_lakehouse_name (str): The lakehouse name of where the administration configurations are located
        - inline_params (dict): Inline parameters that will overwrite and take precedence over the parameters in the administration lakehouse configuration
        - one_lake_endpoint (str): The one lake endpoint. Default is `onelake.dfs.fabric.microsoft.com`
        - mssparkutils_client: MSSparkUtilsClientBase, spark utils client
        """
        super().__init__(spark=spark,
                         workspace_name=workspace_name,
                         solution_name=solution_name,
                         admin_lakehouse_name=admin_lakehouse_name,
                         inline_params=inline_params,
                         one_lake_endpoint=one_lake_endpoint,
                         mssparkutils_client=mssparkutils_client)

    def _setup(self) -> None:
        """
        Setup method for the OMOPIngestionService
        """
        # Disable metrics poller as we are collecting metrics at the end of the activity
        self.metrics_polling_interval_min = 0 
        
        ExtensionParser.register(self.spark)
        
        self.source_lakehouse_name = self.parameter_service.get_foundation_config_value(GC.SILVER_LAKEHOUSE_ID_KEY)
        self.target_lakehouse_name = self.parameter_service.get_foundation_config_value(GC.OMOP_LAKEHOUSE_ID_KEY)
        self.vocab_lakehouse_name = self.parameter_service.get_foundation_config_value(GC.BRONZE_LAKEHOUSE_ID_KEY)
        
        Utils.validate_required_parameters({
            GC.BRONZE_LAKEHOUSE_ID_KEY: self.vocab_lakehouse_name,
            GC.SILVER_LAKEHOUSE_ID_KEY: self.source_lakehouse_name,
            GC.OMOP_LAKEHOUSE_ID_KEY: self.target_lakehouse_name
        })
        
        try:
            self.config_files_root_path = (
                FolderPath.get_fabric_workload_files_root_path(
                    workspace_name=self.workspace_name,
                    one_lake_endpoint=self.one_lake_endpoint,
                    solution_name=self.solution_name,
                )
            )
            
            self.vocabulary_path = self.parameter_service.get_activity_config_value(
                GC.VOCAB_PATH_KEY,
                FolderPath.get_fabric_vocab_folder_path(
                        root_path=FolderPath.get_fabric_files_path(
                            workspace_name=self.workspace_name,
                            one_lake_endpoint=self.one_lake_endpoint,
                            lakehouse_name=self.vocab_lakehouse_name,
                        )
                    )
            )
            self.vocab_ingestion_checkpoint_path = self.parameter_service.get_activity_config_value(
                GC.VOCAB_CHECKPOINT_PATH_KEY,
                FolderPath.get_fabric_workload_files_checkpoint_folder_path(
                    root_path=self.config_files_root_path,
                    checkpoint_folder_name=GC.VOCAB_CHECKPOINT_FOLDER,
                ),
            )
            self.omop_config_path = self.parameter_service.get_activity_config_value(
                GC.OMOP_CONFIG_PATH_KEY,
                FolderPath.get_fabric_workload_files_omop_config_folder_path(root_path=self.config_files_root_path),
            )
            
            self.omop_scripts_path = self.parameter_service.get_activity_config_value(
                GC.OMOP_SCRIPTS_PATH_KEY,
                FolderPath.get_fabric_workload_files_omop_scripts_folder_path(root_path=self.config_files_root_path),
            )
            
            self.source_tables_path = self.parameter_service.get_activity_config_value(
                GC.SOURCE_TABLES_PATH_KEY,
                FolderPath.get_fabric_tables_path(
                    workspace_name=self.workspace_name,
                    one_lake_endpoint=self.one_lake_endpoint,
                    lakehouse_name=self.source_lakehouse_name,
                )
            )
            
            self.omop_tables_path = self.parameter_service.get_activity_config_value( 
                GC.TARGET_TABLES_PATH_KEY,
                FolderPath.get_fabric_tables_path(
                    workspace_name=self.workspace_name,
                    one_lake_endpoint=self.one_lake_endpoint,
                    lakehouse_name=self.target_lakehouse_name,
                )
            )
            
            self.dtt_secondary_lake_path = self.parameter_service.get_activity_config_value(
                GC.DTT_SECONDARY_LAKE_PATH_KEY,
                FolderPath.get_fabric_workload_files_dtt_secondary_lake_folder_path(
                    root_path=self.config_files_root_path
                )
            )
            
            self.dmf_config_path = self.parameter_service.get_activity_config_value(
                GC.DMF_CONFIG_PATH_KEY,
                FolderPath.get_dmf_configuration_files(
                    root_path=self.config_files_root_path
                )
            )
            
            self.rmt_config_path = self.parameter_service.get_activity_config_value(
                GC.RMT_CONFIG_PATH_KEY,
                FolderPath.get_rmt_configuration_files(
                    root_path=self.config_files_root_path
                )
            )
                
            self.dtt_dir = self.parameter_service.get_activity_config_value(
                GC.DTT_ROOT_DIR_PATH_KEY,
                FolderPath.get_fabric_workload_dtt_file_path(
                    root_path=self.config_files_root_path
                )
            )
            
            self.env_config_path = f"{self.dtt_dir}/{GC.ENV_CONFIG_PATH}"
            self.rmt_mapping_input_dir = self.parameter_service.get_activity_config_value(
                GC.RMT_MAPPING_INPUT_DIR_PATH_KEY,
                FolderPath.get_fabric_workload_files_rmt_mapping_folder_path(
                    root_path=self.config_files_root_path
                )
            )
        except Exception as ex:
            self._logger.error(message=str(ex))
            raise

        self.placeholder_values: Dict = {
            "@omopDatabaseSchema": f"`{self.target_lakehouse_name}`"
        }

        # db config to read src storage, check if it exists
        self.dtt_env_config = f"""{{
            "storage": {{
                "source": {{
                    "entities": {{
                        "default": {{
                            "location": "{self.source_tables_path}",
                            "format": "delta"
                        }}
                    }}
                }},
                "target": {{
                    "entities": {{
                        "default": {{
                            "location": "{self.omop_tables_path}",
                            "format": "delta"
                        }}
                    }}
                }},
                "secondary_lake": {{
                    "location": "{self.dtt_secondary_lake_path}"
                }}
            }}
        }}"""

        self.rmt_input = f"""{{
            "query":
                {{
                    "tables": [
                        {{
                            "name": "concept",
                            "path" : "{self.omop_tables_path}/concept"
                        }},
                        {{
                            "name": "concept_relationship",
                            "path" : "{self.omop_tables_path}/concept_relationship"
                        }},
                        {{
                            "name": "vocabulary",
                            "path" : "{self.omop_tables_path}/fhir_system_to_omop_vocab_mapping"
                        }}
                    ],
                    "sql": "with unique_relationship as (select *, row_number() over (partition by concept_id_1 order by valid_start_date desc) as row_number from concept_relationship WHERE relationship_id = 'Maps to') select cr.concept_id_2 as target_value , concat_ws('<->', c.concept_code, fv.Fhir_Uri) as source_value from concept c inner join vocabulary fv on c.vocabulary_id = fv.vocabulary_id left outer join unique_relationship cr on c.concept_id = cr.concept_id_1 and cr.relationship_id = 'Maps to' and cr.row_number = 1 UNION select c.concept_id as target_value, concat_ws('<->', c.concept_code, fv.Fhir_Uri,'NH') as source_value from CONCEPT c inner join vocabulary fv on c.vocabulary_id = fv.vocabulary_id"
                }}
            }}"""

    def _setup_execution_metadata(self) -> ExecutionMetadata:
        source_lakehouse_properties = self.mssparkutils_client.get_lakehouse(self.source_lakehouse_name)   
        target_lakehouse_properties = self.mssparkutils_client.get_lakehouse(self.target_lakehouse_name)
        return ExecutionMetadata(
            sourceType=ExecutionDataType.deltaTable,
            sourcePath=self.source_tables_path,
            sourceLakehouseName=source_lakehouse_properties.get("displayName"),
            sourceLakehouseIdentifier=source_lakehouse_properties.get("id"),
            targetType=ExecutionDataType.deltaTable,
            targetPath=self.omop_tables_path,
            targetLakehouseName=target_lakehouse_properties.get("displayName"),
            targetLakehouseIdentifier=target_lakehouse_properties.get("id")
        )

    def _get_internal_activity_name(self) -> str:
        return GC.OMOP_INGESTION_ACTIVITY_NAME

    def _execute(self, **kwargs) -> None:
        """
        Executes the OMOPIngestionService
        
        Keyword Args:
            transformation_fn (Callable, optional): The transformation function to be executed on the input data. Defaults to None.
        """
        self.__ingest()
        
    def ingest_vocab_data(self):
        """
        Call the VocabularyIngestionService to ingest data into omop vocab tables
        """
        vocabulary_ingestion_service = VocabularyIngestionService(
            spark=self.spark,
            target_tables_path=self.omop_tables_path,
            vocabulary_path=self.vocabulary_path,
            checkpoint_path=self.vocab_ingestion_checkpoint_path,
        )
        vocabulary_ingestion_service.ingest_vocab_data(
            vocab_schema=GC.OMOP_VOCAB_SCHEMA,
            collect_metrics_fn=self.collect_target_delta_table_operation_summary_metrics
        )

    def __ingest(self):
        """Using DTT ingest source data into OMOP tables"""
        
        try:
            # Ingest OMOP Vocab data
            self.ingest_vocab_data()

            # Call DTT to transform Data
            self.__dtt_workflow()

            target_tables = Utils.get_target_anchor_tables_from_dtt_config(
                spark=self.spark,
                dtt_config_path=f"{self.omop_config_path}/{GC.DMF_ADAPTER_FILE}"
            )
            self.collect_all_target_tables_metrics(
                table_names=target_tables, 
                target_tables_root_path=self.omop_tables_path
            )
            
        except Exception as ex:
            self._logger.error(
                f"{LC.OMOP_TRANSFORMATION_EXCEPTION_ERROR_MSG.format(str(ex), traceback.print_exc())}"
            )
            raise

    def __dtt_workflow(self):
        """Invokes the dtt workflow"""
        rmt_mapping_input_file_path = f"{self.rmt_mapping_input_dir}/concept.json"
        rmt_mapping_folder_path = [f"{self.rmt_mapping_input_dir}"]

        # todo: rmt being updated to take file contents vs. path, once ready remove logic below
        # Please note that the current logic creates the Concept.json under in the DMHCheckpoint workload folder i.e `abfss://{workspace_name}@{one_lake_endpoint}/{solution_name}/DMHCheckpoint/dtt/mapping`
        self.mssparkutils_client.fs_put(self.env_config_path, self.dtt_env_config, overwrite=True)
        self.mssparkutils_client.fs_mkdirs(self.rmt_mapping_input_dir)
        self.mssparkutils_client.fs_put(rmt_mapping_input_file_path, self.rmt_input, overwrite=True)

        self._logger.info(
            f"{LC.RMT_CREATED_CONCEPT_FILE.format(self.rmt_mapping_input_dir)}"
        )
        
        dtt_adapter = f"{self.omop_config_path}/{GC.DMF_ADAPTER_FILE}"
        db_target_schema = f"{self.omop_config_path}/{GC.DB_TARGET_SCHEMA}"
        db_target_schema_config = (
            f"{self.omop_config_path}/{GC.DB_TARGET_SCHEMA_CONFIG}"
        )
        db_semantics = f"{self.omop_config_path}/{GC.DB_SEMANTICS}"
        db_semantics_config = (
            f"{self.omop_config_path}/{GC.DB_SEMANTICS_CONFIG}"
        )
        
        config_files = {
            "adaptor_file_location": dtt_adapter,
            "target_db_semantics_file_location": db_semantics,
            "env_config_file_location": self.env_config_path,
            "target_db_schema_file_location": db_target_schema,
            "db_schema_config_location": db_target_schema_config,           
            "target_db_semantics_config_file_location": db_semantics_config,
        }
        
        dtt_workflow = DTTWorkflowService( 
            spark=self.spark,   
            rmt_out_path=self.rmt_config_path,
            dtt_out_path=self.dmf_config_path,
            config_files=config_files,
            rmt_ordered_mapping_definitions_folders=rmt_mapping_folder_path,
            mssparkutils_client=self.mssparkutils_client,
        )
        dtt_workflow.execute_dtt_workflow()   