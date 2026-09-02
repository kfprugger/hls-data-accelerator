# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
import os
from pyspark.sql import SparkSession
from microsoft.fabric.hls.hds.utils.logging_helper import LoggingHelper
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.sdoh.bronze_ingestion.constants import SdohConstants
from microsoft.fabric.hls.hds.sdoh.bronze_ingestion.core_process import CoreProcess
from microsoft.fabric.hls.hds.sdoh.bronze_ingestion.utils import SdohUtils
from microsoft.fabric.hls.hds.utils.business_events_ingestion_handler import BusinessEventsIngestion
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase
from microsoft.fabric.hls.hds.utils.utils import Utils as PlatformCommonUtil
from datetime import datetime
from pyspark.sql.types import StructType, StructField, StringType, TimestampType, LongType, BinaryType
from pyspark.sql import DataFrame
import time, uuid

class Orchestrator:

    def __init__(self,
                 spark: SparkSession,
                 source_lakehouse_name: str,
                 target_lakehouse_name: str,
                 bronze_tables_path: str,
                 sdoh_drop_folder_path: str,
                 sdoh_process_folder_path: str,
                 sdoh_failed_folder_path: str,
                 business_events_ingestion_service: BusinessEventsIngestion,
                 checkpoint_path: str,
                 mssparkutils_client: MSSparkUtilsClientBase,
                 collect_source_and_target_metrics_fn
                 ) -> None:
        """
        Class which is responsible for orchestrating the SDOH Bronze Ingestion process.

        Args:
            - spark: Spark session
            - bronze_tables_path: Path for the target tables
            - fabric_files_path: Path for the fabric files
            - sdoh_drop_folder_path: The path for folder which has SDOH public datasets
            - sdoh_process_folder_path: The SDOH process folder
            - sdoh_failed_folder_path: The Failed files folder
            - checkpoint_path: The path for the checkpoint
            - mssparkutils_client: MSSpark client instance or test instance
        """
        self.spark: SparkSession = spark
        self.source_lakehouse_name = source_lakehouse_name
        self.target_lakehouse_name = target_lakehouse_name
        self.bronze_tables_path = bronze_tables_path
        self.sdoh_drop_folder_path = sdoh_drop_folder_path
        self.sdoh_process_folder_path = sdoh_process_folder_path
        self.sdoh_failed_folder_path = sdoh_failed_folder_path
        self.business_events_ingestion_service = business_events_ingestion_service
        self.checkpoint_path = checkpoint_path
        self.mssparkutils_client = mssparkutils_client
        self._collect_source_and_target_metrics_fn = collect_source_and_target_metrics_fn
        self._logger = LoggingHelper.get_sdoh_bronze_ingestion_logger(
            self.spark, self.__class__.__name__, GlobalConstants.LOGGING_LEVEL
        )
        self.timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        self.utils = SdohUtils()
        self.lst_processed_files = []
        self.coreProcessor = CoreProcess(self.spark, self.source_lakehouse_name, self.target_lakehouse_name, self.bronze_tables_path, self.sdoh_failed_folder_path, self.business_events_ingestion_service, self._logger, self.mssparkutils_client,
                                         self._collect_source_and_target_metrics_fn)
        
    def start_ingestion(self) -> None:
        """
        Start the SDOH Bronze Ingestion process.
        This method moves files from the drop folder to the process folder, processes the files,
        and writes the processed data to a Delta table.
        Raises:
            Exception: If an error occurs during the ingestion process.
        """
        try:
            if PlatformCommonUtil.path_exists(self.sdoh_process_folder_path, mssparkutils_client=self.mssparkutils_client):
             self._process_with_checkpoint()
            else:
                message = LC.PATH_NOT_EXIST_ERR_MSG.format(process_name=LC.SDOH_BRONZE_INGESTION_PROCESS_NAME,path=self.sdoh_drop_folder_path)
                self._logger.error(message)
                new_row = self.business_events_ingestion_service.create_new_business_event_row(id=str(uuid.uuid4()), activityName=GlobalConstants.SDOH_BRONZE_INGESTION_ACTIVITY_NOTEBOOK, 
                    targetFilePath= self.sdoh_process_folder_path, targetLakehouseName= self.target_lakehouse_name,
                    sourceFilePath= self.sdoh_drop_folder_path, sourceLakehouseName= self.source_lakehouse_name, severity= GlobalConstants.ERROR, 
                    eventType= GlobalConstants.SDOH_MOVE_FROM_DROP_TO_PROCESS_FOLDER , message= message, active=True) 
                self.business_events_ingestion_service.insert_business_events([new_row])
                
        except Exception as ex:
            if not self.coreProcessor.exceptions:
                self._logger.error(message=str(ex))
                new_row = self.business_events_ingestion_service.create_new_business_event_row(id=str(uuid.uuid4()), activityName=GlobalConstants.SDOH_BRONZE_INGESTION_ACTIVITY_NOTEBOOK, 
                    targetFilePath= self.sdoh_process_folder_path,targetLakehouseName= self.target_lakehouse_name,
                    sourceFilePath= self.sdoh_drop_folder_path, sourceLakehouseName= self.source_lakehouse_name, severity= GlobalConstants.ERROR, 
                    eventType= GlobalConstants.SDOH_MOVE_FROM_DROP_TO_PROCESS_FOLDER, message= str(ex), exception= str(ex), active=True)
                self.business_events_ingestion_service.insert_business_events([new_row])
            
            raise

    def _process_with_checkpoint(self):
        """
        Process the SDOH public data sets with a checkpoint.

        This method reads binary files as a stream, processes them using the `_process_sdoh_files` method,
        and writes the processed data to a Delta table.
        """
        try:
            process_file_path = f"{self.sdoh_process_folder_path}"
            df_stream = self._read_binary_file_as_stream(process_file_path)
            query = (
                df_stream.writeStream
                .trigger(availableNow=True)
                .format("delta")
                .option("checkpointLocation", self.checkpoint_path)
                .foreachBatch(lambda df, epoch_id: self._process_sdoh_files(df))
                .start()
            )
            query.awaitTermination()
        except Exception as error:
            if self.coreProcessor.exceptions:
                for exception in self.coreProcessor.exceptions:
                    self.business_events_ingestion_service.insert_business_events([exception])
            raise Exception(error)

    def _process_sdoh_files(self, df: DataFrame) -> None:
        """
        Process the SDOH files
        Args:
        - df: DataFrame containing the SDOH files
        """
        csv_ingested=True
        excel_ingested = True
        self.spark.sparkContext.setJobGroup(f"{self.__class__.__module__}.{self.__class__.__qualname__}", "Processing SDOH dataframe")
        total_files = df.count()
        source_data_size_bytes = df._jdf.queryExecution().optimizedPlan().stats().sizeInBytes()
        
        if df is None or total_files == 0:
            self._logger.info(LC.EMPTY_PROCESS_PATH.format(process_path=self.sdoh_process_folder_path))
            return
        
        try:
            df.cache()
            csv_row = df.filter(df.path.endswith(SdohConstants.FILETYPE_CSV))
            excel_row = df.filter((df.path.endswith(SdohConstants.FILETYPE_XLSX)) | (df.path.endswith(SdohConstants.FILETYPE_XLS)))
            csv_ingested = self.coreProcessor.ingest_csv(csv_row, self.timestamp, self.lst_processed_files)
            excel_ingested = self.coreProcessor.ingest_excel(excel_row, self.lst_processed_files)
            message = LC.SDOH_PROCESSED_FILES_INFO_MSG.format(total_files_processed=self.lst_processed_files)
            distinct_path_count = df.select("path").distinct().count()
            self._collect_source_and_target_metrics_fn(
                metrics={
                    "sourceDataSizeBytes": source_data_size_bytes,
                    "numSourceFiles": distinct_path_count,
                },
                delta_table_path=None
            )            
            self._logger.info(message)
            if not (csv_ingested and excel_ingested):
                raise Exception(f"{LC.SDOH_BRONZE_DATASET_INGESTION_FALIURE}")
            
        except Exception as ex:
            exception_message = f"{LC.INGESTION_FAILURE.format(error_message=str(ex))}"
            if (csv_ingested and excel_ingested):
                error_message = f"{LC.MOVE_FAILED_FILES_FAILED_FOLDER}"
                self._logger.error(error_message)
                df_unprocessed_files = df[~df.path.isin(self.lst_processed_files)]
                self.utils._move_files_to_failed_folder(df_unprocessed_files, self.sdoh_failed_folder_path, self.mssparkutils_client)
                
                new_row = self.business_events_ingestion_service.create_new_business_event_row(id=str(uuid.uuid4()), activityName=GlobalConstants.SDOH_BRONZE_INGESTION_ACTIVITY_NOTEBOOK, 
                    targetFilePath= self.bronze_tables_path,targetLakehouseName= self.target_lakehouse_name,
                    sourceFilePath= self.sdoh_process_folder_path, sourceLakehouseName= self.source_lakehouse_name, severity= GlobalConstants.ERROR, 
                    eventType= GlobalConstants.SDOH_DELTA_TABLE_CREATION_FROM_PROCESS_FOLDER, message= error_message, exception= exception_message, active=True)
                self.business_events_ingestion_service.insert_business_events([new_row])
            raise Exception(exception_message)   

    def _move_files_with_timestamp(self, source_path: str, target_path: str) -> None:
        """
        Move files from the source path to the target path, appending a timestamp to the file names.

        Args:
            source_path (str): The path of the source directory.
            target_path (str): The path of the target directory.

        Returns:
            None
        """
        if PlatformCommonUtil.path_exists(source_path, mssparkutils_client=self.mssparkutils_client):
            files = PlatformCommonUtil.list_files(
                source_path, mssparkutils_client=self.mssparkutils_client)
            directories = [item.path for item in files if item.isDir]

            for subdir in directories:
                files_in_subdir = PlatformCommonUtil.list_files(
                    subdir, mssparkutils_client=self.mssparkutils_client)
                for file in files_in_subdir:
                    if not file.isDir:
                        # Get the base name of the file
                        base_name = os.path.basename(file.path)

                        # Append the timestamp to the base name
                        new_name = f"{self.timestamp}_{base_name}"

                        # Construct the new path
                        new_subdir = subdir.replace(source_path, target_path)
                        PlatformCommonUtil.create_folder(
                            new_subdir, mssparkutils_client=self.mssparkutils_client)
                        new_path = os.path.join(new_subdir, new_name)

                        # Move the file to the new path
                        PlatformCommonUtil.move_folders_files(
                            file.path, new_path, mssparkutils_client=self.mssparkutils_client)
                # Remove the source subdirectory after moving all the files
                PlatformCommonUtil.remove_dir(
                    subdir, mssparkutils_client=self.mssparkutils_client, recursive=True)

    def _read_binary_file_as_stream(self, processed_path: str) -> DataFrame:
        """
        Reads a binary file as a streaming DataFrame.

        Args:
            processed_path (str): The path to the processed binary file.

        Returns:
            DataFrame: A streaming DataFrame containing the binary file data.

        """
        # Define the schema for the binary file
        binary_file_schema = StructType([
            StructField("path", StringType(), True),
            StructField("modificationTime", TimestampType(), True),
            StructField("length", LongType(), True),
            StructField("content", BinaryType(), True)
        ])

        # Read the file as a binary data stream
        glob_pattern = "*.{csv,xlsx,xls}"
        df = self.spark.readStream.format('binaryFile') \
        .schema(binary_file_schema)  \
        .option("recursiveFileLookup", True) \
        .option("pathGlobFilter",glob_pattern) \
        .option("basePath", processed_path) \
        .load(processed_path)
        return df