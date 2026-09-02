# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
"""
Module with a class to generate ndjson files for fhir resource data from dicom tags
"""
from pyspark.sql import SparkSession, DataFrame
from pyspark import StorageLevel
from pyspark.sql.types import *
from pyspark.sql.functions import *
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.utils.logging_helper import LoggingHelper
from microsoft.fabric.hls.hds.medical_imaging.dicom.core.constants import ImagingStudyConstants as C
from microsoft.fabric.hls.hds.medical_imaging.dicom.utils.utils import Utils
import json
from datetime import datetime, timezone
import uuid
from microsoft.fabric.hls.hds.medical_imaging.dicom.utils.dicom_to_fhir_utils import DicomToFhirUtils
from microsoft.fabric.hls.hds.medical_imaging.dicom.core.dicom_metadata_udf import extract_alphabetic, transform_to_date, transform_to_time
from microsoft.fabric.hls.hds.utils.fhir_converter_helper import FHIRConverter 
from microsoft.fabric.hls.hds.utils.utils import FolderPath
from microsoft.fabric.hls.hds.utils.utils import Utils as CommonUtils
from microsoft.fabric.hls.hds.structured_stream.delta_table_stream_reader import DeltaTableStreamReader
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase
from microsoft.fabric.hls.hds.utils.dataframe_utils import find_managed_delta_table_using_path
from microsoft.fabric.hls.hds.utils.business_events_ingestion_handler import BusinessEventsIngestion
from microsoft.fabric.hls.hds.services.base_runnable_service import BaseRunnableService
from microsoft.fabric.hls.hds.data_models.execution_metadata import ExecutionMetadata, ExecutionDataType


class MetadataToFhirConvertor(BaseRunnableService):
    """
    This is a class used to generate ndjson files for fhir resource data from dicom tags
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
            - workspace_name: Name of the Fabric Workspace
            - solution_name (str): Name of the HDS-Healthcare data solutions OneLake workload solution
            - admin_lakehouse_name (str): The lakehouse name of where the administration configurations are located
            - inline_params (dict): Inline parameters that will overwrite and take precedence over the parameters in the administration lakehouse configuratio
            - one_lake_endpoint (str): The one lake endpoint. Default is `onelake.dfs.fabric.microsoft.com`
            - mssparksutils_client (MSSparkUtilsClientBase): The mssparkutils client
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
        The setup method for initializing the MetadataToFhirConvertor variables
        """
        self.lakehouse_name = self.parameter_service.get_foundation_config_value(GC.BRONZE_LAKEHOUSE_ID_KEY)

        self.silver_lakehouse_name = self.parameter_service.get_foundation_config_value(GC.SILVER_LAKEHOUSE_ID_KEY)

        self.config_files_root_path = FolderPath.get_fabric_workload_files_root_path(
            workspace_name=self.workspace_name,
            one_lake_endpoint=self.one_lake_endpoint,
            solution_name=self.solution_name
        )
        
        self.config_file_path = self.parameter_service.get_activity_config_value(
            GC.DICOM_TO_FHIR_CONFIG_PATH_KEY,
            f"{self.config_files_root_path}/{GC.DEFAULT_DICOM_CONFIGS_PATH}/{C.DICOM_TO_FHIR_MAPPING_FILE_NAME}"
        )

        self.mapping_config = json.loads(
            self.spark.sparkContext.wholeTextFiles(
                self.config_file_path
            ).collect()[0][1]
        )
        
        self.table_schema_file_path = self.parameter_service.get_foundation_config_value(
            GC.IMAGING_TABLE_SCHEMA_PATH_KEY,
            f"{self.config_files_root_path}/{GC.DEFAULT_DICOM_CONFIGS_PATH}/{C.DICOM_TABLES_SCHEMA_FILE_NAME}"
        )
        self.table_schema = json.loads(
            self.spark.sparkContext.wholeTextFiles(
                self.table_schema_file_path
            ).collect()[0][1]
        )

        self.field_by_name = Utils.get_field_type_with_tags_not_null(
            self.table_schema,
            C.METADATA_TABLE_NAME,
            C.NDJSON_IGNORE_FIELDS
        )

        self.checkpoint_path = self.parameter_service.get_activity_config_value(
            GC.CHECKPOINT_PATH_KEY,
            FolderPath.get_fabric_workload_files_checkpoint_folder_path(
                root_path=self.config_files_root_path,
                checkpoint_folder_name=f"{GC.MEDICAL_IMAGING_CONFIG_FOLDER}/{C.DICOM_TO_FHIR_CHECKPOINT_FOLDER}")
        )
        self.avro_schema_file_path = self.parameter_service.get_activity_config_value(
            GC.AVRO_SCHEMA_PATH_KEY,
            f"{FolderPath.get_fabric_workload_files_schema_root_folder_path(root_path=self.config_files_root_path)}/{GC.DEFAULT_SILVER_LAKEHOUSE_NAME}"
        )

        self.imaging_study_avro_schema_path = f"{self.avro_schema_file_path}/{C.FHIR_IMAGING_STUDY_RES_NAME.lower()}{C.AVRO_SCHEMA_FILE_EXT}"
        self.spark_schema = CommonUtils.load_schema_from_avro_schema(
            self.spark, 
            CommonUtils.load_config_file(
                self.spark, 
                self.imaging_study_avro_schema_path
            )
        )
        
        self.lakehouse_files_root_path = FolderPath.get_fabric_files_path(
            workspace_name=self.workspace_name,
            one_lake_endpoint=self.one_lake_endpoint,
            lakehouse_name=self.lakehouse_name
        )
        
        self.fhir_ndjson_files_root_path = self.parameter_service.get_activity_config_value(
            GC.FHIR_NDJSON_FILES_ROOT_PATH_KEY,
            f"{self.lakehouse_files_root_path}/{GC.DEFAULT_LANDINGZONE_SOURCE_PATTERN}"
        )
        
        self.delta_table_path = self.parameter_service.get_foundation_config_value(
            GC.IMAGING_DELTA_TABLE_PATH_KEY,
            FolderPath.get_fabric_tables_path(
                workspace_name=self.workspace_name,
                one_lake_endpoint=self.one_lake_endpoint,
                lakehouse_name=self.lakehouse_name
            )
        )
        
        self.metastore_table_path = self.parameter_service.get_activity_config_value(
        GC.IMAGING_METASTORE_TABLE_PATH_KEY,
        FolderPath.get_fabric_tables_path(
            workspace_name=self.workspace_name,
            one_lake_endpoint=self.one_lake_endpoint,
            lakehouse_name=self.silver_lakehouse_name
            )
        )
        
        self.max_records_per_ndjson = int(self.parameter_service.get_activity_config_value(GC.MAX_RECORDS_PER_NDJSON_KEY, C.MAX_RECORDS_PER_NDJSON))
        self.fhir_convertor = FHIRConverter(C.FHIR_IMAGING_STUDY_RES_NAME, self.mapping_config, self.spark_schema, C.SOURCE_MODIFIED_COLUMN_NAME)
        
        self.max_files_per_trigger = int(self.parameter_service.get_activity_config_value(GC.MAX_FILES_PER_TRIGGER_KEY, C.D2F_MAX_FILES_PER_TRIGGER))
        self.max_bytes_per_trigger = self.parameter_service.get_activity_config_value(GC.MAX_BYTES_PER_TRIGGER_KEY, C.D2F_MAX_BYTES_PER_TRIGGER, "int")
        
        self.business_events_ingestion_service = BusinessEventsIngestion(
            spark = self.spark,
            workspace_name = self.workspace_name,
            one_lake_endpoint = self.one_lake_endpoint,
            lakehouse_name = self.admin_lakehouse_name,
            solution_name = self.solution_name,
            parameter_service = self.parameter_service
        )
    
    def _setup_execution_metadata(self) -> ExecutionMetadata:
        return ExecutionMetadata(
            sourceType=ExecutionDataType.deltaTable,
            sourcePath=self.delta_table_path,
            sourceLakehouseName= self.mssparkutils_client.get_lakehouse(self.lakehouse_name).get("displayName"),
            sourceLakehouseIdentifier=self.mssparkutils_client.get_lakehouse(self.lakehouse_name).get("id"),
            targetType=ExecutionDataType.file,
            targetLakehouseName=self.mssparkutils_client.get_lakehouse(self.lakehouse_name).get("displayName"),
            targetLakehouseIdentifier=self.mssparkutils_client.get_lakehouse(self.lakehouse_name).get("id"),
            targetPath=self.fhir_ndjson_files_root_path
        )
    
    def _get_internal_activity_name(self) -> str:
        return GC.IMAGING_FHIR_NDJSON_CONVERSION_ACTIVITY_NAME
    
    def _execute(self, **kwargs) -> None:
        """
        Executes the execute_ndjson_generation function to generate NDJSON    
        Keyword Args:
            transformation_fn (Callable, optional): The transformation function to be executed on the input data. Defaults to None.        
        """
        self.execute_ndjson_generation()
        
    def _generate_ndjson_and_save(self, df: DataFrame, epoch_id: str):
        """
        This method is used to generate fhir ndjson files from dicom metastore table
        """   
        
        self.spark.sparkContext.setJobGroup(
            f"{self.__class__.__module__}.{self.__class__.__qualname__}",
            f"Counting records for epoch_id: {epoch_id}"
        )
        df_count = df.count()
        if df_count == 0:
            self._logger.info(LC.NO_NEW_DATA_FOUND_INFO_MSG)
            return
        
        self._logger.info(LC.FHIR_CONVERSION_PROCESS_STATE_INFO_MSG.format(
            epoch_id = epoch_id,
            state = C.STATE_STARTED,
            timestamp = datetime.now(),
            table_loc = self.delta_table_path
        ))
        
        self._logger.info(LC.RECORDS_NUM_PROCESSED_INFO_MSG.format(
            records_num = df_count
        ))
                
        df = DicomToFhirUtils.pre_process_dataframe(df,
                                                    find_managed_delta_table_using_path
                                                    (self.spark, 
                                                    f"{self.metastore_table_path}/{C.IMAGING_META_STORE}")
                                                    .toDF())
        df = self.normalize_dicom_metadata(df)
        
        #handling update scenario- if there exists multiple rows for a dcm file (based on study, series, instance id)
        #take the row with latest sourceModifiedAt column value
        df = FHIRConverter.remove_intermediate_updates(df, C.GROUP_BY_ELEMENTS['instance'], C.SOURCE_MODIFIED_COLUMN_NAME)
        
        self._logger.info(LC.FHIR_ELEMENT_GROUPING_INFO_MSSG.format(
            fhir_element_name=C.FHIR_SERIES_ELEMENT
        ))
        
        #aggregating information at series level
        series_level_agg = self.fhir_convertor._df_groupby_and_agg(df, C.FHIR_SERIES_ELEMENT,C.GROUP_BY_ELEMENTS)
    
        #joining aggregated information at series level with the original dataframe
        df = df.join(series_level_agg, C.GROUP_BY_ELEMENTS[C.FHIR_SERIES_ELEMENT], "leftouter")
        
        self._logger.info(LC.FHIR_ELEMENT_GROUPING_INFO_MSSG.format(
            fhir_element_name=C.FHIR_IMAGING_STUDY_RES_NAME
        ))

        
        #aggregating information at ImagingStudy level
        study_level_agg = self.fhir_convertor._df_groupby_and_agg(df, C.FHIR_IMAGING_STUDY_RES_NAME,C.GROUP_BY_ELEMENTS, [C.FHIR_SERIES_ELEMENT]) 
        study_level_agg = study_level_agg.withColumn(C.FHIR_IMAGING_STUDY_RES_NAME, to_json(col(C.FHIR_IMAGING_STUDY_RES_NAME)))
        study_level_agg = study_level_agg.select(C.FHIR_IMAGING_STUDY_RES_NAME, C.SOURCE_SYSTEM_COLUMN_NAME).persist(StorageLevel.MEMORY_AND_DISK)
        
        self._logger.info(LC.IMAGING_STUDY_OBJECTS_PROCESSED_INFO_MSG.format(
            num_records=study_level_agg.count()
        ))
        
        distinct_src_systems = study_level_agg.select(C.SOURCE_SYSTEM_COLUMN_NAME).distinct()
        self.spark.sparkContext.setJobGroup(f"{self.__class__.__module__}.{self.__class__.__qualname__}", "Collecting distinct source systems")
        distinct_src_systems_list = distinct_src_systems.rdd.map(lambda row: row[0]).collect()
        
        total_ndjson_count:int = 0
        total_imaging_study_count:int=0
        for source_system in distinct_src_systems_list:
            self.fhir_namespace = source_system
            img_study_rows = study_level_agg.filter(study_level_agg[C.SOURCE_SYSTEM_COLUMN_NAME] == source_system).select(C.FHIR_IMAGING_STUDY_RES_NAME)
            imaging_study_list = img_study_rows.rdd.map(lambda row: row[0]).collect()
            
            self._logger.info(LC.IMAGING_STUDY_OBJECTS_PER_SOURCE_INFO_MSG.format(
                num_records=len(imaging_study_list),
                source_system=self.fhir_namespace
            ))
            
            #json cleanup
            imaging_study_list = [
                json.dumps(
                    FHIRConverter.cleanup_json(
                        json.loads(study), self.mapping_config
                    )) 
                for study in imaging_study_list
            ]
        
            #splitting the records into multiple ndjson files
            data_split = self.fhir_convertor._split_ndjson_data(self.max_records_per_ndjson,imaging_study_list)
            total_ndjson_count = total_ndjson_count + len(data_split)
            total_imaging_study_count = total_imaging_study_count + len(imaging_study_list)
            self.fhir_convertor._save_ndjson_files(self.fhir_namespace,self.fhir_ndjson_files_root_path,self.mssparkutils_client,data_split)
            
        # Collect the execution metrics for logging purposes
        self.execution_metrics_collector.accumulate(
            accumulator_activity_id=self.get_execution_metrics_accumulator_activity_id(),
            metrics={                    
                "numSourceRecords": df_count,
                "batchesProcessed": 1,
                "numTargetFiles": total_ndjson_count,
                "activityAttributes": {        
                    "totalImagingStudyRecords": total_imaging_study_count }                
            }
        )
           
        study_level_agg.unpersist(False)
           
        self._logger.info(LC.FHIR_CONVERSION_PROCESS_STATE_INFO_MSG.format(    
            epoch_id = epoch_id,
            state = C.STATE_COMPLETED,
            timestamp = datetime.now(),
            table_loc = self.delta_table_path
            ))
        
            
    def execute_ndjson_generation(self):        
        try:
            self.spark.sparkContext.setJobGroup(f"{self.__class__.__module__}.{self.__class__.__qualname__}", "Executing NDJSON generation")
            stream_reader = DeltaTableStreamReader(self.spark,
                                    maxFilesPerTrigger= self.max_files_per_trigger,
                                    maxBytesPerTrigger= self.max_bytes_per_trigger)
            
            df = stream_reader.set_up_streaming(
                f"{self.delta_table_path}/{C.METADATA_TABLE_NAME}"
            ).drop(C.TAGS_JSON_COLUMN_NAME, C.TAGS_METADATA_STRING)
        
            query = (df.writeStream.format("delta")
                .trigger(availableNow=True)
                .option("checkpointLocation", self.checkpoint_path)
                .foreachBatch(self._generate_ndjson_and_save)
                .start())
        
            query.awaitTermination()
        except Exception as e:
            self._logger.error(
                LC.SPARK_STREAM_READ_ERR_MSG.format(
                    table_path = self.delta_table_path,
                    error_msg = str(e)
                )
            )
            
            # Insert a row into Business Events table
            business_events_failed_row = self.business_events_ingestion_service.create_new_business_event_row(
                id =str(uuid.uuid4())
                , activityName =    C.IMAGING_NOTEBOOK_D2F
                , targetFilePath=   self.fhir_ndjson_files_root_path
                , sourceTableName = C.METADATA_TABLE_NAME
                , sourceLakehouseName= f"{self.lakehouse_name}"
                , targetLakehouseName= f"{self.lakehouse_name}" 
                , sourceFilePath=   f"{self.delta_table_path}/{C.METADATA_TABLE_NAME}"  
                , runId =           self.pipeline_run_id   
                , severity =        GC.ERROR
                , eventType=        C.BE_EVENT_TYPE_D2F_EXECUTE_NDJSON_GENERATION
                , message=   LC.SPARK_STREAM_READ_ERR_MSG.format(table_path = self.delta_table_path,error_msg = str(e))
                , exception= str(e)                
            )
            self.business_events_ingestion_service.insert_business_events([business_events_failed_row])
           
            raise
        
    def normalize_dicom_metadata(self, df: DataFrame) -> DataFrame:
        """
        This method is used to normalize the dicom metadata dataframe
        Args:
            df (DataFrame): dataframe with dicom metadata
        
        Returns:        
            DataFrame: normalized dataframe
        """
        # Normalize the DICOM metadata by converting the tags to a string representation
        df_transformed = df.drop(C.TAGS_METADATA_STRING, C.ID_COLUMN_NAME)

        udf_transform_to_date = udf(transform_to_date, StringType())
        udf_transform_to_time = udf(transform_to_time, StringType())
        udf_extract_alphabetic_udf = udf(extract_alphabetic, StringType())

        # Define a mapping from VR to the transformation UDF
        vr_udf_map = {
            "PN": udf_extract_alphabetic_udf,
            "DA": udf_transform_to_date,
            "TM": udf_transform_to_time,
        }      

        for tag_displayName, tag_info in self.field_by_name.items():
            tag_metadata = tag_info.metadata
            tag_path = col(C.TAGS_JSON_COLUMN_NAME).getItem(tag_metadata['tag'])
            vr = tag_path.getItem("vr")
            value = tag_path.getItem("Value")

            # Handle ArrayType fields separately
            if isinstance(tag_info.dataType, ArrayType):
                # For arrays, we take the whole array value
                df_transformed = df_transformed.withColumn(tag_displayName, value.cast(tag_info.dataType))
                continue
            
            transformed_col = value.getItem(0)

            # This avoids checking all VR types for every field
            final_col = when(vr == "PN", vr_udf_map["PN"](transformed_col)) \
                        .when(vr == "DA", vr_udf_map["DA"](transformed_col)) \
                        .when(vr == "TM", vr_udf_map["TM"](transformed_col)) \
                        .otherwise(transformed_col)

            # Add the new column, casting to the correct type
            df_transformed = df_transformed.withColumn(
                tag_displayName,
                when(value.getItem(0).isNotNull(), final_col.cast(tag_info.dataType))
                .otherwise(lit(None))
            )

        df_transformed = df_transformed.drop(C.TAGS_JSON_COLUMN_NAME)
                
        return df_transformed