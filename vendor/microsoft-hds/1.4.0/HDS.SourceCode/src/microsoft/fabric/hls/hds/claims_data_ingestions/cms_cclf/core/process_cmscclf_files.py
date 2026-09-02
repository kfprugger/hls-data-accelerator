import json
import os
from urllib.parse import unquote
import uuid
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import col, input_file_name, length, regexp_extract,substring_index
from datetime import datetime
from microsoft.fabric.hls.hds.medical_imaging.dicom.utils.utils import Utils
from microsoft.fabric.hls.hds.utils.business_events_ingestion_handler import BusinessEventsIngestion
from microsoft.fabric.hls.hds.utils.utils import Utils as CommonUtils
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase
from microsoft.fabric.hls.hds.claims_data_ingestions.cms_cclf.core.constants import CmsCclfConstants
from microsoft.fabric.hls.hds.claims_data_ingestions.cms_cclf.core.dataExtractor import DataExtractor
from microsoft.fabric.hls.hds.claims_data_ingestions.cms_cclf.utils.utils import add_new_literal_column_for_input_value, max_file_size_validation, remove_invalid_cms_cclf_files, move_file_to_folder
from microsoft.fabric.hls.hds.utils.dataframe_utils import add_current_timestamp_column
from microsoft.fabric.hls.hds.utils.logging_helper import LoggingHelper
from microsoft.fabric.hls.hds.utils.dataframe_utils import append_to_delta_table_using_path
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from typing import Callable


class Process_CmsCclf_Files:
    """
    Class for processing CMS CCLF files.
    Args:
        spark (SparkSession): The Spark session object.
        cms_cclf_files_drop_path (str): The path to the drop folder for CMS CCLF files.
        lakehouse_files_root_path (str): The root path for the lakehouse files.
        mssparkutils_client (MSSparkUtilsClientBase, optional): The MSSparkUtilsClientBase object for interacting with Azure Blob Storage. Defaults to None.
    """

    def __init__(self, spark: SparkSession, cms_cclf_files_drop_path: str, lakehouse_files_root_path: str, supported_file_extensions: list,
                 business_events_ingestion_service: BusinessEventsIngestion,
                 collect_metrics_fn: Callable = None,
                 execution_metrics_collector = None,
                 execution_metrics_accumulator_id: str = "",
                 mssparkutils_client: MSSparkUtilsClientBase = None) -> None:
        """
        Initializes an instance of the ProcessCmsCclfFiles class.
        Args:
            spark (SparkSession): The SparkSession object.
            cms_cclf_files_drop_path (str): The path to the CMS CCLF files drop location.
            lakehouse_files_root_path (str): The root path of the lakehouse files.
            mssparkutils_client (MSSparkUtilsClientBase, optional): The MSSparkUtilsClientBase object. Defaults to None.
        Returns:
            None
        """
        
        self.spark = spark
        self.cms_cclf_files_drop_path = cms_cclf_files_drop_path
        self.lakehouse_files_root_path = lakehouse_files_root_path
        self._logger = LoggingHelper.get_generic_logger(self.spark, self.__class__.__name__, GlobalConstants.LOGGING_LEVEL)        
        self._mssparkutils_client = CommonUtils.get_mssparkutils_client(mssparkutils_client)
        self.supported_file_extension_array = supported_file_extensions
        self.failed_files_path = os.path.join(self.lakehouse_files_root_path, 
                                              GlobalConstants.FAILED_FOLDER,
                                              GlobalConstants.CLAIMS_FOLDER,
                                              GlobalConstants.CCLF_FOLDER, 
                                              datetime.now().strftime("%Y/%m/%d"))
        self.business_events_ingestion_service = business_events_ingestion_service
        self._collect_metrics_fn = collect_metrics_fn
        self._execution_metrics_collector = execution_metrics_collector
        self._execution_metrics_accumulator_id = execution_metrics_accumulator_id                        
    
    def process(self, cclf_files_config_path: str, checkpoint_path: str, target_delta_tables_path: str, max_files_per_trigger: int):
        """
        Process the CMS CCLF files.
        Args:
            cclf_files_config_path (str): The path to the CCLF files configuration.
            checkpoint_path (str): The path to the checkpoint location.
            target_delta_tables_path (str): The path to the target delta tables.
            max_files_per_trigger (int): maximum number of files to process per micro-batch.
        Raises:
            Exception: If an error occurs during the process.
        Returns:
            None
        """        
        try:
            self.cclf_files_config_path = cclf_files_config_path
            self.target_delta_tables_path = target_delta_tables_path
            self.checkpoint_path = checkpoint_path
            self.max_files_per_trigger = max_files_per_trigger
            
        except Exception as ex:
            self._logger.error(LC.CMS_CCLF_CONFIG_NOT_FOUND_ERROR_MSG.format(message=str(ex)))
            raise       

        
        self._logger.info(LC.CMS_CCLF_STARTED_READING_FILE_CONFIG_MSG)
        
        self.file_config = json.loads(
            self.spark.sparkContext.wholeTextFiles(
                self.cclf_files_config_path
            ).collect()[0][1]
        )
        
        self._logger.info(LC.CMS_CCLF_COMPLETED_READING_FILE_CONFIG_MSG)
        
        self.extractor = DataExtractor(self.spark)
        
        try:
            df_stream = self.extractor.read_data_files_to_df_stream(self.cms_cclf_files_drop_path, self.max_files_per_trigger)
        except Exception as ex:
            self._logger.error(
                LC.CMS_CCLF_SPARK_STREAM_READ_ERR_MSG.format(
                    drop_folder = self.cms_cclf_files_drop_path,
                    error_msg = str(ex)))
            raise

        self._logger.info(LC.CMS_CCLF_READING_PROCESS_INFO_MSG.format(state=CmsCclfConstants.CMS_CCLF_SPARK_READ_COMPLETED,
                                                                         drop_folder=self.cms_cclf_files_drop_path))

        self._logger.info(LC.CMS_CCLF_PROCESS_START_INFO_MSG.format(
        process_name=CmsCclfConstants.CMS_CCLF_PROCESS, 
        state= CmsCclfConstants.CMS_CCLF_BATCH_PROCESSING_STARTED))
        df_stream = add_new_literal_column_for_input_value(df_stream , CmsCclfConstants.CMS_CCLF_FILE_PATH_NAME, input_file_name())
        df_stream = df_stream.withColumn(CmsCclfConstants.CMS_CCLF_FILE_TYPE_NAME, substring_index(df_stream[CmsCclfConstants.CMS_CCLF_FILE_PATH_NAME], ".", -1))
        df_stream = df_stream.withColumn(CmsCclfConstants.SOURCE_SYSTEM_COLUMN_NAME, regexp_extract(input_file_name(), r".*\/" + GlobalConstants.CLAIMS_FOLDER + r"\/[^\/]+\/([^\/]+)\/", 1))
        
        self.spark.sparkContext.setJobGroup(f"{self.__class__.__module__}.{self.__class__.__qualname__}", "Processing CMS CCLF files")
        query = (df_stream.writeStream.format('delta')
                .trigger(availableNow=True)
                .option("checkpointLocation", f"{self.checkpoint_path}")
                .foreachBatch(lambda df, epoch_id: self._process_cms_cclf_batch_records(df, CmsCclfConstants.FAILED_NUM_RETRIES)).start())
        query.awaitTermination()
        
        self._logger.info(LC.CMS_CCLF_PROCESS_START_INFO_MSG.format(
        process_name=CmsCclfConstants.CMS_CCLF_PROCESS, 
        state= CmsCclfConstants.CMS_CCLF_BATCH_PROCESSING_COMPLETED))
    
    def _process_cms_cclf_batch_records(self,df:DataFrame, num_retries: int):
        """
        Process the CMS CCLF batch records.
        Args:
            df (DataFrame): The input DataFrame containing the batch records.
            num_retries (int): The number of retries for processing.
        Returns:
            None
        Raises:
            None
        """
    
        self.spark.sparkContext.setJobGroup(
            f"{self.__class__.__module__}.{self.__class__.__qualname__}",
            f"[CMS_CCLF] Processing CMS CCLF batch record"
        )
        total_records = df.count()
        source_data_size_bytes = df._jdf.queryExecution().optimizedPlan().stats().sizeInBytes()
        
        if total_records == 0:
            self._logger.info(LC.CMS_CCLF_CLAIMS_NO_RECORDS_MSG)
            return
        
        if(num_retries < 0):
            #moving files for which processing failed to failed folder
            if total_records > 0:
                try:
                    for row in df.collect():
                        Utils.move_files(row.filepath, os.path.join(self.failed_files_path, os.path.basename(row.filepath)), self._mssparkutils_client, True)
                except Exception as e:
                    self._logger.error(LC.FAILED_FILES_NOT_MOVED_ERR_MSG.format(
                        error_msg=str(e)
                    ))
            return
            
        self._logger.info(LC.RETRY_INFO_MSG.format(
            process_name= CmsCclfConstants.CMS_CCLF_PROCESS_NAME, 
            retry_attempt=abs(num_retries-CmsCclfConstants.FAILED_NUM_RETRIES)+1))        
        
        distinct_file_paths_df = df.select(CmsCclfConstants.CMS_CCLF_FILE_PATH_NAME).distinct()
        max_files_lst = max_file_size_validation(self, distinct_file_paths_df, CmsCclfConstants.CMS_CCLF_MAX_FILE_SIZE_IN_MB)
        
        without_max_file_sizes_df = df.filter(~col(CmsCclfConstants.CMS_CCLF_FILE_PATH_NAME).isin(max_files_lst))
        valid_df_stream = without_max_file_sizes_df.filter(col(CmsCclfConstants.CMS_CCLF_FILE_TYPE_NAME).isin(self.supported_file_extension_array)).cache()
        invalid_df_stream = without_max_file_sizes_df.filter(~col(CmsCclfConstants.CMS_CCLF_FILE_TYPE_NAME).isin(self.supported_file_extension_array))
        unique_file_ext_df = valid_df_stream.select(CmsCclfConstants.CMS_CCLF_FILE_TYPE_NAME).distinct().collect()
        remove_invalid_cms_cclf_files(self, invalid_df_stream, self.failed_files_path)
        
        max_file_path = ""
        message = ""
        max_file_size = str(CmsCclfConstants.CMS_CCLF_MAX_FILE_SIZE_IN_MB)
        max_file_size_exceed_lst = []    
        
        if self._execution_metrics_collector and total_records > 0:
            # Collect source data metrics
            self._execution_metrics_collector.accumulate(
                accumulator_activity_id=self._execution_metrics_accumulator_id,
                metrics={
                    "numSourceRecords": total_records,
                    "sourceDataSizeBytes": source_data_size_bytes,
                    "numSourceFiles": distinct_file_paths_df.count(),
                }
            )
        
        for file_path in max_files_lst:
            max_file_path = ""
            message = ""
            max_file_path = unquote(file_path)
            message = LC.CMS_CCLF_FILE_WITH_MAX_SIZE_MOVES_TO_FAILED_FOLDER_MSG.format(file = file_path, 
                                                                                    max_file_size = (max_file_size + str("MB")))
            move_file_to_folder(max_file_path, self.failed_files_path, self._mssparkutils_client)
            self._logger.info(message)
            id = str(uuid.uuid4())
            new_row = self.business_events_ingestion_service.create_new_business_event_row(id= id, activityName=GlobalConstants.CMSCCLF_CLAIMS_LANDINGZONE_TO_DELTATABLE_INGESTION_NOTEBOOK, 
                                                    targetFilePath= self.failed_files_path, sourceFilePath= max_file_path, severity= GlobalConstants.ERROR, 
                                                    eventType= GlobalConstants.CMSCCLF_CLAIMS_MAX_FILE_SIZE_EXCEED, message= message, 
                                                    exception=GlobalConstants.CMSCCLF_CLAIMS_MAX_FILE_SIZE_EXCEED_EXCEPTION_MESSAGE.format(max_file_size=max_file_size), active=True)          
            max_file_size_exceed_lst.append(new_row)
        
        self.business_events_ingestion_service.insert_business_events(max_file_size_exceed_lst)
                
        key, file_extension, target_delta_table = "", "", ""
                        
        for value in unique_file_ext_df:
                            
            file_extension = value.file_type
            self._logger.info(LC.CMS_CCLF_PROCESS_START_INFO_MSG.format(process_name=CmsCclfConstants.CMS_CCLF_FILE_SPECIFIC_NAME,
                                                                    state= LC.CMS_CCLF_FILE_STARTED_FOR_MSG))
            
            for k in CmsCclfConstants.Files_Config:
                file_ext = str(CmsCclfConstants.Files_Config[k]()[1]).replace("*.","")
                if file_ext == str(file_extension):
                    key = k                
                
            self._logger.info(LC.CMS_CCLF_PROCESS_START_INFO_MSG.format(
            process_name=CmsCclfConstants.CMS_CCLF_PROCESS_NAME, 
            state= CmsCclfConstants.CMS_CCLF_BATCH_PROCESSING_STARTED + key))
            
            if key is not None and key != "":
                if CmsCclfConstants.Files_Config[key]()[0] is not None and CmsCclfConstants.Files_Config[key]()[1] is not None:
                    target_delta_table = CmsCclfConstants.Files_Config[key]()[0]
            else:
                self._logger.error(LC.CMS_CCLF_INVALID_FILE_EXTENSION_MSG)
                return
            
            if target_delta_table is not None and target_delta_table != "":
                target_delta_table = os.path.join(self.target_delta_tables_path , target_delta_table)
                
            cclf_file_config = self.file_config[key]
            col_spec = cclf_file_config[CmsCclfConstants.CMS_CCLF_COLUMN_SPECIFICATION] 
            field_spec = cclf_file_config[CmsCclfConstants.CMS_CCLF_FIELD_NAMES]
            
            last_col_spec_position = 0
            for value in col_spec:
                last_col_spec_position = last_col_spec_position + value
            
            
            cms_cclf_file_specific_df = valid_df_stream.where(col(CmsCclfConstants.CMS_CCLF_FILE_TYPE_NAME) == file_extension)
            lineItem_length_not_matching_df = cms_cclf_file_specific_df.where(length(col("value")) != last_col_spec_position)
            line_item_length_not_matching_file_size_lst = []
            line_item_length_not_matching_file_size_paths_lst = []
            error_message = ""
            
            
            for data in lineItem_length_not_matching_df.collect():
                id = str(uuid.uuid4())
                current_row_file_path = data.filePath
                error_message = LC.CMS_CCLF_FILE_WITH_ATLEAST_ONE_RECORD_NOT_MATCHING_EXPECTED_LENGTH_MSG.format(file = current_row_file_path)
                new_row = self.business_events_ingestion_service.create_new_business_event_row(id=id,activityName= GlobalConstants.CMSCCLF_CLAIMS_LANDINGZONE_TO_DELTATABLE_INGESTION_NOTEBOOK, targetTableName= target_delta_table,
                                        targetFilePath= self.failed_files_path, sourceFilePath= current_row_file_path, 
                                        severity= GlobalConstants.ERROR, eventType= GlobalConstants.CMSCCLF_CLAIMS_CURRENT_LINE_ITEM_LENGTH_NOT_MATCHING,
                                        active=True, message= GlobalConstants.CMSCCLF_CLAIMS_CURRENT_LINE_ITEM_LENGTH_NOT_MATCHING_MESSAGE.format(value= data.value, file_extension= file_extension),
                                        exception= error_message)
                line_item_length_not_matching_file_size_lst.append(new_row)
            
            self.business_events_ingestion_service.insert_business_events(line_item_length_not_matching_file_size_lst)
            
            error_message = ""
            
            if lineItem_length_not_matching_df.isEmpty():
                self._logger.info(LC.CMS_CCLF_LINE_ITEM_LENGTH_MATCHING_MSG.format(file_extension=file_extension))
            else:
                for row in lineItem_length_not_matching_df.select(CmsCclfConstants.CMS_CCLF_FILE_PATH_NAME).distinct().collect():
                    current_row_file_path = row.filePath
                    line_item_length_not_matching_file_size_paths_lst.append(current_row_file_path)
                    error_message = LC.CMS_CCLF_FILE_WITH_ATLEAST_ONE_RECORD_NOT_MATCHING_EXPECTED_LENGTH_MSG.format(file = current_row_file_path)
                    move_file_to_folder(unquote(current_row_file_path), self.failed_files_path, self._mssparkutils_client)
                    self._logger.info(error_message)
                        
            cms_cclf_file_specific_df = cms_cclf_file_specific_df.filter(~(col(CmsCclfConstants.CMS_CCLF_FILE_PATH_NAME).isin(line_item_length_not_matching_file_size_paths_lst)))
            
            cclf_file_field_col_dic = {field: spec for field, spec in zip(field_spec, col_spec)}
        
            startPosition: int = 1
            starting_col_spec: int = 0
        
            for key, value in cclf_file_field_col_dic.items():
                starting_col_spec = value               
                cms_cclf_file_specific_df = cms_cclf_file_specific_df.withColumn(key, col("value").substr(startPosition, starting_col_spec))
                startPosition = startPosition + starting_col_spec
            
            cms_cclf_file_specific_df = cms_cclf_file_specific_df.drop("value")
            cms_cclf_file_specific_df = cms_cclf_file_specific_df.drop(CmsCclfConstants.CMS_CCLF_FILE_TYPE_NAME)
            cms_cclf_file_specific_df = add_current_timestamp_column(cms_cclf_file_specific_df, GlobalConstants.DEFAULT_BRONZE_CREATED_DATE_COL)
            
            try:          
                append_to_delta_table_using_path(
                df_to_process=cms_cclf_file_specific_df,
                delta_table_path=target_delta_table,
                logger=self._logger,
                collect_metrics_fn=self._collect_metrics_fn
            )
            except Exception as ex:
                self._logger.error(
                    LC.CMS_CCLF_DELTA_TABLE_WRITE_STREAM_ERR_MSG.format(
                        error_msg=str(ex)
                    )
                )
                self._process_cms_cclf_batch_records(df, num_retries-1)
                raise
            
            successful_record_insertion_lst = []
            id = str(uuid.uuid4())
            successful_record_insertion_row = self.business_events_ingestion_service.create_new_business_event_row(id= id, activityName= GlobalConstants.CMSCCLF_CLAIMS_LANDINGZONE_TO_DELTATABLE_INGESTION_NOTEBOOK, targetTableName= target_delta_table,
                                                            targetFilePath= target_delta_table, severity= GlobalConstants.INFO, 
                                                            eventType=GlobalConstants.CMSCCLF_CLAIMS_DELTA_TABLE_RECORD_INSERTION_SUCCESS_MESSAGE,
                                                            active=False,message= GlobalConstants.RECORD_INSERTION_SUCCESS.format(count=cms_cclf_file_specific_df.count(),
                                                                                                                                target_delta_table = target_delta_table))
            
            successful_record_insertion_lst.append(successful_record_insertion_row)          
            self.business_events_ingestion_service.insert_business_events(successful_record_insertion_lst)
            
            self._logger.info(LC.CMS_CCLF_PROCESS_START_INFO_MSG.format(process_name=CmsCclfConstants.CMS_CCLF_FILE_SPECIFIC_NAME,
                                                                state= LC.CMS_CCLF_FILE_PROCESSING_COMPLETED_MSG))