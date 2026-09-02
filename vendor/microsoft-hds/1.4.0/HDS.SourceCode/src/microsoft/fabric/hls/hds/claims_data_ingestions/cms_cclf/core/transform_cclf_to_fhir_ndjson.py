import os
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, DoubleType, BooleanType, TimestampType,DecimalType,DateType
from pyspark.sql.functions import col, when, lit, collect_set, to_json, struct, current_timestamp,array
from microsoft.fabric.hls.hds.claims_data_ingestions.cms_cclf.utils.utils import check_tables_exist
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.utils.dataframe_utils import prepare_source_data
from microsoft.fabric.hls.hds.utils.logging_helper import LoggingHelper
from microsoft.fabric.hls.hds.claims_data_ingestions.cms_cclf.core.constants import CmsCclfConstants as C
import json, uuid
from datetime import datetime
from microsoft.fabric.hls.hds.utils.business_events_ingestion_handler import BusinessEventsIngestion
from microsoft.fabric.hls.hds.utils.fhir_converter_helper import FHIRConverter 
from microsoft.fabric.hls.hds.utils.utils import FolderPath
from microsoft.fabric.hls.hds.utils.utils import Utils as CommonUtils
from microsoft.fabric.hls.hds.structured_stream.delta_table_stream_reader import DeltaTableStreamReader
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase
from microsoft.fabric.hls.hds.utils.parameter_service import ParameterService
from microsoft.fabric.hls.hds.services.base_runnable_service import BaseRunnableService
from microsoft.fabric.hls.hds.data_models.execution_metadata import ExecutionMetadata, ExecutionDataType
from microsoft.fabric.hls.hds.errors.transform_to_fhir_ndjson_service_failed_error import TransformToFHIRNDJSONServiceFailedError


class TransformCCLFToFHIRNDJSON(BaseRunnableService):
    """
    This is a class used to generate ndjson files for fhir resource data from CCLF
    """

    def __init__(self, 
                 spark: SparkSession,
                 workspace_name: str,
                 solution_name: str,
                 admin_lakehouse_name: str,
                 inline_params: dict = None,
                 one_lake_endpoint: str = GC.DEFAULT_ONE_LAKE_ENDPOINT,
                 mssparkutils_client: MSSparkUtilsClientBase = None) -> None:
        """
        Args:
            - spark: spark session
            - workspace_name (str): Name of the Fabric Workspace
            - solution_name (str): Name of the HDS-Healthcare data solutions OneLake workload solution
            - admin_lakehouse_name (str): The lakehouse name of where the administration configurations are located
            - inline_params (dict): Inline parameters that will overwrite and take precedence over the parameters in the administration lakehouse configuration
            - one_lake_endpoint (str): The one lake endpoint. Default is `onelake.dfs.fabric.microsoft.com`
            - mssparksutils_client (MSSparkUtilsClientBase): The mssparkutils client
        """     
        super().__init__(
            spark=spark,
            workspace_name=workspace_name,
            solution_name=solution_name,
            admin_lakehouse_name=admin_lakehouse_name,
            inline_params=inline_params,
            one_lake_endpoint=one_lake_endpoint,
            mssparkutils_client=mssparkutils_client
        )
        
    def _setup(self) -> None:
        
        self.config_files_root_path = FolderPath.get_fabric_workload_files_root_path(
            workspace_name=self.workspace_name,
            one_lake_endpoint=self.one_lake_endpoint,
            solution_name=self.solution_name
        )
        
        self.target_lakehouse_name = self.source_lakehouse_name = self.parameter_service.get_foundation_config_value(GC.BRONZE_LAKEHOUSE_ID_KEY)
        self.config_file_path = self.parameter_service.get_activity_config_value(
            GC.CONFIG_FILE_PATH_KEY,
            f"{self.config_files_root_path}/{GC.DEFAULT_CCLF_TO_FHIR_CONFIG_PATH}/{C.CCLF_TO_FHIR_MAPPING_FILE_NAME}"
        )
        
        self.mapping_config = json.loads(
            self.spark.sparkContext.wholeTextFiles(
                self.config_file_path
            ).collect()[0][1]
        )
        
        self.checkpoint_path = os.path.join(
            self.parameter_service.get_foundation_config_value(
            GC.CLAIMS_CHECKPOINT_PATH_KEY,
            FolderPath.get_fabric_workload_files_checkpoint_folder_path(
                root_path=self.config_files_root_path,
                checkpoint_folder_name=f"{GC.CLAIMS_INGESTION_FOLDER}"
            )
        ),C.CCLF_TO_FHIR_CHECKPOINT_FOLDER)
        self.avro_schema_file_path = self.parameter_service.get_activity_config_value(
            GC.AVRO_SCHEMA_PATH_KEY,
            f'{FolderPath.get_fabric_workload_files_schema_root_folder_path(root_path=self.config_files_root_path)}/{GC.DEFAULT_SILVER_LAKEHOUSE_NAME}'
        )

        self.ndjson_file_metrics = {}
        self.explanationofbenefit_avro_schema_path = f"{self.avro_schema_file_path}/{C.FHIR_EOB_ELEMENT.lower()}{C.AVRO_SCHEMA_FILE_EXT}"
        self.spark_schema = CommonUtils.load_schema_from_avro_schema(
            self.spark, 
            CommonUtils.load_config_file(
                self.spark, 
                self.explanationofbenefit_avro_schema_path
            )
        )
        
        self.lakehouse_files_root_path = FolderPath.get_fabric_files_path(
            workspace_name=self.workspace_name,
            one_lake_endpoint=self.one_lake_endpoint,
            lakehouse_name=self.source_lakehouse_name
        )
        self.fhir_ndjson_files_root_path = self.parameter_service.get_activity_config_value(
            GC.FHIR_NDJSON_FILES_ROOT_PATH_KEY,
            f"{self.lakehouse_files_root_path}/{GC.DEFAULT_LANDINGZONE_SOURCE_PATTERN}"
        )
        self.fhir_namespace = self.parameter_service.get_activity_config_value(GC.FHIR_NAMESPACE_KEY, C.FHIR_NAMESPACE)
        self.delta_table_path = self.parameter_service.get_activity_config_value(
            GC.DELTA_TABLE_PATH_KEY,
            FolderPath.get_fabric_tables_path(
                workspace_name=self.workspace_name,
                one_lake_endpoint=self.one_lake_endpoint,
                lakehouse_name=self.source_lakehouse_name
            )
        )
        self.fhir_convertor = FHIRConverter(C.FHIR_EOB_ELEMENT,self.mapping_config,self.spark_schema, C.HEADERTABLE_SCHEMA_CREATEDDATE)
        self._execution_metrics_collector=self.execution_metrics_collector

        self.business_events_table_path = FolderPath.get_fabric_tables_path(
            workspace_name=self.workspace_name,
            one_lake_endpoint=self.one_lake_endpoint,
            lakehouse_name=self.admin_lakehouse_name)
        
        self.business_events_schema_dir_path = self.parameter_service.get_activity_config_value(
                GC.BUSINESS_EVENTS_SCHEMA_DIR_PATH_KEY,
                f"{FolderPath.get_fabric_workload_files_schema_root_folder_path(root_path=self.config_files_root_path)}/{GC.BUSINESS_EVENTS_SCHEMA_ROOT_FOLDER}"
            )

        self.business_events_schema_path = f"{self.business_events_schema_dir_path}/{GC.BUSINESS_EVENTS_TABLE}{C.AVRO_SCHEMA_FILE_EXT}"
        
        self.business_events_ingestion_service = BusinessEventsIngestion(
                spark = self.spark,
                workspace_name = self.workspace_name,
                one_lake_endpoint = self.one_lake_endpoint,
                lakehouse_name = self.admin_lakehouse_name,
                solution_name = self.solution_name,
                parameter_service = self.parameter_service
                )
        
        try:
            self.max_records_per_ndjson = int(self.parameter_service.get_activity_config_value(GC.MAX_RECORDS_PER_NDJSON_KEY, C.MAX_RECORDS_PER_NDJSON))
        except Exception as ex:
            self._logger.error(message=str(ex))
            raise

        self.claims_view_name = C.CLAIMS_DELTA_VIEWNAME.format(lakehouse_name=self.source_lakehouse_name,view_name=C.VIEWNAME)
    

    def _get_internal_activity_name(self) -> str:
        return GC.CMS_CCLF_FILES_BRONZE_INGESTION_ACTIVITY_NAME

    def _register_custom_accumulators(self) -> None:
        # Register any custom counters if needed
        self.execution_metrics_collector.register_accumulator(
            accumulator_activity_id=self._get_validation_metrics_accumulator_activity_id(),
            initial_state=self._get_validation_metrics_initial_state()
        )

    def _setup_execution_metadata(self) -> ExecutionMetadata:
        return ExecutionMetadata(
            sourceType=ExecutionDataType.deltaTable,
            sourcePath=self.delta_table_path,
            targetType=ExecutionDataType.file,
            targetPath=self.fhir_ndjson_files_root_path,
            sourceLakehouseName=self.mssparkutils_client.get_lakehouse(self.source_lakehouse_name).get("displayName"),
            sourceLakehouseIdentifier=self.mssparkutils_client.get_lakehouse(self.source_lakehouse_name).get("id"),
            targetLakehouseName=self.mssparkutils_client.get_lakehouse(self.target_lakehouse_name).get("displayName"),
            targetLakehouseIdentifier=self.mssparkutils_client.get_lakehouse(self.target_lakehouse_name).get("id"),
        )
   
    def generate_createview_sqlquery(self,min_created_datetime) -> str:
        """
        Generates the SQL query for selecting data, joining all Claims Part files.

        Returns:
            str: The select query for the joined data.
        """
        # Check if all required tables exist
        allCCLFTablesExist = check_tables_exist(self, C.CCLF_TABLES_LIST)
        
        if allCCLFTablesExist:
            # Return the select query
            return C.SELECT_CLAIMS_QUERY.format(minCreatedDatetime=min_created_datetime)
        return None
       
    def _generate_ndjson_and_save(self, df: DataFrame, epoch_id: str):
        """
        This method is used to generate fhir ndjson files from CCLF delta table
        """ 
        self.spark.sparkContext.setJobGroup(
            f"{self.__class__.__module__}.{self.__class__.__qualname__}",
            f"Generating NDJSON and saving | Epoch ID: {epoch_id}"
        )
        id = str(uuid.uuid4())
        total_records = df.count()
        source_data_size_bytes = df._jdf.queryExecution().optimizedPlan().stats().sizeInBytes()

        if total_records == 0:
            new_row = self.business_events_ingestion_service.create_new_business_event_row(id=id, activityName=GC.CMSCCLF_CLAIMS_CCLF_FHIR_CONVERSION, 
                                                    targetFilePath= self.fhir_ndjson_files_root_path, sourceTableName= C.CCLF1_CLAIMS_HEADER, 
                                                    sourceFilePath= self.delta_table_path, sourceLakehouseName= GC.DEFAULT_BRONZE_LAKEHOUSE_NAME, severity= GC.INFO, 
                                                    eventType= GC.CMSCCLF_CLAIMS_NO_RECORS_GENERATE_NDJSON_AND_SAVE, message= LC.CCLF_NO_NEW_DATA_FOUND_INFO_MSG, 
                                                    active=False) 
            self.business_events_ingestion_service.insert_business_events([new_row])
            self._logger.info(LC.CCLF_NO_NEW_DATA_FOUND_INFO_MSG)
            return
                
        self._logger.info(LC.CCLF_FHIR_CONVERSION_PROCESS_STATE_INFO_MSG.format(
            epoch_id = epoch_id,
            state = C.STATE_STARTED,
            timestamp = datetime.now(),
            table_loc = self.delta_table_path
            ))
        self._logger.info(LC.CCLF_SQL_QUERY_EXECUTION_STARTED_INFO_MSG.format(
            view_name = self.claims_view_name, timestamp = datetime.now()
            ))
        # Prepare the source data by filtering for only one unique record
        df = prepare_source_data(input_df=df,
                                    unique_columns= C.GROUP_BY_ELEMENTS[C.FHIR_EOB_ELEMENT],
                                    timestamp_column= C.HEADERTABLE_SCHEMA_CREATEDDATE)
    
        # Sort the dataframe by 'min_created_datetime' in ascending order and take the first row
        min_created_datetime = df.orderBy(C.HEADERTABLE_SCHEMA_CREATEDDATE).select(C.HEADERTABLE_SCHEMA_CREATEDDATE).first()[0]
        
        # Create view if does not exist
        eobViewQuery = self.generate_createview_sqlquery(min_created_datetime)
        
        if eobViewQuery is None:
            message = LC.CCLF_VIEW_CREATION_FAILED_ERR_MSG.format(view_name = self.claims_view_name)
            new_row = self.business_events_ingestion_service.create_new_business_event_row(id=id, activityName=GC.CMSCCLF_CLAIMS_CCLF_FHIR_CONVERSION, 
                                                    targetFilePath= self.fhir_ndjson_files_root_path, sourceTableName= C.CCLF1_CLAIMS_HEADER, 
                                                    sourceFilePath= self.delta_table_path, sourceLakehouseName= GC.DEFAULT_BRONZE_LAKEHOUSE_NAME, severity= GC.ERROR, 
                                                    eventType= GC.CMSCCLF_CLAIMS_FAILED_GENERATE_NDJSON_AND_SAVE, message= message, 
                                                    active=True) 
            self.business_events_ingestion_service.insert_business_events([new_row])
            
            self._logger.error(message)
            return
        eob_delta_view = self.spark.sql(eobViewQuery)
        
        df = df.join(eob_delta_view,C.GROUP_BY_ELEMENTS[C.FHIR_EOB_ELEMENT])
        self._logger.info(LC.CCLF_SQL_QUERY_EXECUTION_COMPLETED_INFO_MSG.format(
            view_name = self.claims_view_name, timestamp = datetime.now()
            ))
        claims_data = self.fhir_convertor._df_groupby_and_agg(df, C.FHIR_EOB_ELEMENT, C.GROUP_BY_ELEMENTS) 
        claims_data = claims_data.withColumn(C.FHIR_EOB_ELEMENT, to_json(col(C.FHIR_EOB_ELEMENT)))
        claims_data = claims_data.select(C.FHIR_EOB_ELEMENT, C.SOURCE_SYSTEM_COLUMN_NAME)

        message = LC.CCLF_RECORDS_NUM_PROCESSED_INFO_MSG.format(
            records_num = claims_data.count()
            )
        
        distinct_src_systems = claims_data.select(C.SOURCE_SYSTEM_COLUMN_NAME).distinct()
        distinct_src_systems_list = distinct_src_systems.rdd.map(lambda row: row[0]).collect()
        
        num_target_files:int = 0
        for source_system in distinct_src_systems_list:
            self.fhir_namespace = source_system
            eob_rows = claims_data.filter(claims_data[C.SOURCE_SYSTEM_COLUMN_NAME] == source_system).select(C.FHIR_EOB_ELEMENT)
            explanationofbenefit_list = eob_rows.rdd.map(lambda row: row[0]).collect()
            
            self._logger.info(LC.CMS_CCLF_OBJECTS_PER_SOURCE_INFO_MSG.format(
                num_records=len(explanationofbenefit_list),
                source_system=self.fhir_namespace
            ))
                      
            explanationofbenefit_list = [
                json.dumps(
                    FHIRConverter.cleanup_json(
                        json.loads(row), self.mapping_config
                    )) 
                for row in explanationofbenefit_list
            ]
            data_split = self.fhir_convertor._split_ndjson_data(self.max_records_per_ndjson,explanationofbenefit_list)
            num_target_files = num_target_files + len(data_split)
            self.fhir_convertor._save_ndjson_files(self.fhir_namespace,self.fhir_ndjson_files_root_path,self.mssparkutils_client,data_split)
            
        self._execution_metrics_accumulator_id=self.get_execution_metrics_accumulator_activity_id()
        if self._execution_metrics_collector:
            self._execution_metrics_collector.accumulate(
                accumulator_activity_id=self._execution_metrics_accumulator_id,
                metrics={
                    "numSourceRecords": total_records,
                    "numSourceRecordsGranular": {C.CCLF1_CLAIMS_HEADER: total_records},
                    "numSourceFiles": len(C.CCLF_TABLES_LIST),
                    "sourceDataSizeBytes": source_data_size_bytes,
                    "batchesProcessed": 1,
                    "numTargetFiles": num_target_files,
                }
            )

        self._logger.info(
            f"NDJSON Generation Summary: {num_target_files} files created at target location."
        )
        
        
        new_row = self.business_events_ingestion_service.create_new_business_event_row(id=id, activityName=GC.CMSCCLF_CLAIMS_CCLF_FHIR_CONVERSION, 
                                                targetFilePath= self.fhir_ndjson_files_root_path, sourceTableName= C.CCLF1_CLAIMS_HEADER, 
                                                sourceFilePath= self.delta_table_path, sourceLakehouseName= GC.DEFAULT_BRONZE_LAKEHOUSE_NAME, severity= GC.INFO, 
                                                eventType= GC.CMSCCLF_CLAIMS_SUCCESS_GENERATE_NDJSON_AND_SAVE, message= message, 
                                                active=False)          
        self.business_events_ingestion_service.insert_business_events([new_row])
            
        
    def execute_ndjson_generation(self):
        """
        Executes the generation of NDJSON (Newline Delimited JSON) from the given Delta table.
        The generated NDJSON is saved to the specified checkpoint location.

        Raises:
            Exception: If an error occurs during the execution.
        """
        try:
            if check_tables_exist(self,C.CCLF_TABLES_LIST):      
                stream_reader = DeltaTableStreamReader(self.spark)
                df = stream_reader.set_up_streaming(
                    f"{self.delta_table_path}/{C.CCLF1_CLAIMS_HEADER}"
                )
            
                self.spark.sparkContext.setJobGroup(f"{self.__class__.__module__}.{self.__class__.__qualname__}", "Executing NDJSON generation and saving")
                query = (df.writeStream.format("delta")
                    .trigger(availableNow=True)
                    .option("checkpointLocation", self.checkpoint_path)
                    .foreachBatch(self._generate_ndjson_and_save)
                    .start())

                query.awaitTermination()
        except Exception as e:
            message = LC.CMS_CCLF_SPARK_STREAM_GENERATE_ERR_MSG.format(error_msg = str(e))
            
            id = str(uuid.uuid4())
            new_row = self.business_events_ingestion_service.create_new_business_event_row(id=id, activityName=GC.CMSCCLF_CLAIMS_CCLF_FHIR_CONVERSION, 
                                                    targetFilePath= self.fhir_ndjson_files_root_path, sourceTableName= C.CCLF1_CLAIMS_HEADER, 
                                                    sourceFilePath= self.delta_table_path, sourceLakehouseName= GC.DEFAULT_BRONZE_LAKEHOUSE_NAME, severity= GC.ERROR, 
                                                    eventType= GC.CMSCCLF_CLAIMS_FAILED_EXECUTE_NDJSON_GENERATION, message= message, 
                                                    active=True)          
            self.business_events_ingestion_service.insert_business_events([new_row])

            self._logger.error(message)
            raise TransformToFHIRNDJSONServiceFailedError(message=str(e))

    def _execute(self, **kwargs) -> None:
        """
        Orchestration of NDJSON transformations
        """
        self.execute_ndjson_generation()