# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
"""
Module with a class containing validation steps for bronze ingestion
"""
import os
import pandas
import json
import uuid
import gzip
import io
import base64
from pathlib import Path
from datetime import datetime
from functools import reduce

from pyspark.sql import SparkSession, Row, DataFrame
from pyspark.sql.functions import (
    col, when, lit, to_json, struct, collect_list, 
    base64, encode, decode, unbase64, expr, explode, 
    from_json, row_number, monotonically_increasing_id
)
from pyspark.sql.types import (
    StructType, StructField, StringType, TimestampType, ArrayType
)
from pyspark.sql.window import Window
from delta.tables import DeltaTable

from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.sdoh.bronze_ingestion.constants import SdohConstants
from microsoft.fabric.hls.hds.sdoh.bronze_ingestion.utils import SdohUtils 
from microsoft.fabric.hls.hds.utils.business_events_ingestion_handler import BusinessEventsIngestion
from microsoft.fabric.hls.hds.sdoh.bronze_ingestion.validator import Validator
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase
from microsoft.fabric.hls.hds.utils.data_manager_logger import DataManagerLogger
from delta import DeltaTable
from pathlib import Path, PosixPath
import uuid

class CoreProcess:

    def __init__(self,
                 spark: SparkSession,
                 source_lakehouse_name: str,
                 target_lakehouse_name: str,
                 bronze_tables_path: str,
                 sdoh_failed_folder_path: str,
                 business_events_ingestion_service: BusinessEventsIngestion,
                 logger: DataManagerLogger,
                 mssparkutils_client: MSSparkUtilsClientBase,
                 collect_source_and_target_metrics_fn) -> None:
        """
        Class to process the SDOH files.

        Args:
            - spark: Spark session
            - bronze_tables_path: Path for the bronze target tables
            - logger: Logger instance
            - mssparkutils_client: MSSpark client instance or test instance
        """
        self.spark: SparkSession = spark
        self.source_lakehouse_name = source_lakehouse_name
        self.target_lakehouse_name = target_lakehouse_name
        self.bronze_tables_path = bronze_tables_path
        self.sdoh_failed_folder_path = sdoh_failed_folder_path
        self.mssparkutils_client = mssparkutils_client
        self._logger = logger
        self.bronze_validator = Validator()
        self.utils = SdohUtils()
        self.business_events_ingestion_service = business_events_ingestion_service
        self._collect_source_and_target_metrics_fn = collect_source_and_target_metrics_fn
        self.exceptions = list()
        self.ingest_exception_excel = None
        self.ingest_exception_csv = None

    def ingest_excel(self, df, list_processed_files) -> bool:
        """
        Ingests an Excel file into the system.
        """
        bool_excel_ingested = True

        for row in df.collect():
            try:
                rowPath = Path(row.path)
                datasetName = rowPath.parent.name
                file_name = os.path.basename(row.path)
                self._logger.info(f"{LC.DATASET_INGESTION_START.format(dataset_name=file_name)}")
                
                try:
                    df_excel_file = pandas.ExcelFile(io.BytesIO(bytes(row.content)))
                except Exception as ex:
                    message = f"{LC.EXCEL_READ_FAILURE.format(file_path=row.path,error_message=str(ex))}"
                    self._logger.error(message)
                    new_row = self.business_events_ingestion_service.create_new_business_event_row(id=str(uuid.uuid4()), activityName=GlobalConstants.SDOH_BRONZE_INGESTION_ACTIVITY_NOTEBOOK, 
                        targetFilePath= self.bronze_tables_path, targetLakehouseName= self.target_lakehouse_name, targetTableName=GlobalConstants.SDOH_BRONZE_TABLE_NAME,
                        sourceFilePath= rowPath, sourceLakehouseName= self.source_lakehouse_name, severity= GlobalConstants.ERROR, 
                        eventType= GlobalConstants.SDOH_READ_EXCEL_FILE_FROM_PATH, message= message, exception= str(ex), active=True)
                    self.ingest_exception_excel = new_row
                    raise Exception(message)

                # Validate the excel dataframe
                validationError = self.bronze_validator.validate_excel_dataset(df_excel_file, row.path)
                if validationError is not None:
                    new_row = self.business_events_ingestion_service.create_new_business_event_row(id=str(uuid.uuid4()), activityName=GlobalConstants.SDOH_BRONZE_INGESTION_ACTIVITY_NOTEBOOK, 
                        targetFilePath= self.bronze_tables_path, targetLakehouseName= self.target_lakehouse_name, targetTableName=GlobalConstants.SDOH_BRONZE_TABLE_NAME,
                        sourceFilePath= rowPath, sourceLakehouseName= self.source_lakehouse_name, severity= GlobalConstants.ERROR, 
                        eventType= GlobalConstants.SDOH_VALIDATE_EXCEL_DATASET_FOR_REQUIRED_SHEETS_AND_COLUMNS, message= validationError, exception= validationError, active=True)
                    self.ingest_exception_excel = new_row
                    raise Exception(validationError)

                # Ingest metadata
                loc_conf_df = df_excel_file.parse(SdohConstants.SHEETNAME_LOCCONFIG)
                if not self.bronze_validator.validate_loc_conf_df(loc_conf_df):
                    message = f"{LC.INVALID_LOC_CONFIG_INFORMATION.format(file_name=row.path)}"
                    new_row = self.business_events_ingestion_service.create_new_business_event_row(id=str(uuid.uuid4()), activityName=GlobalConstants.SDOH_BRONZE_INGESTION_ACTIVITY_NOTEBOOK, 
                        targetFilePath= self.bronze_tables_path, targetLakehouseName= self.target_lakehouse_name, targetTableName=GlobalConstants.SDOH_BRONZE_TABLE_NAME,
                        sourceFilePath= rowPath, sourceLakehouseName= self.source_lakehouse_name, severity= GlobalConstants.ERROR, 
                        eventType= GlobalConstants.SDOH_VALIDATE_LOCATION_CONFIGURATION_DATAFRAME, message= message, exception= message, active=True)
                    self.ingest_exception_excel = new_row
                    raise Exception(message)
                    
                loc_conf = self.utils.prepare_location_configuration(loc_conf_df)
                loc_columns = self.utils.get_locationColumns(loc_conf_df)
                metadata_result = self._ingest_metadata(df_excel_file.parse(SdohConstants.SHEETNAME_METADATA, parse_dates=[
                                                    SdohConstants.PUBLISHED_DATE, SdohConstants.VALIDITY_DATE]), loc_conf, row.path)
                hash_sdmd = metadata_result["metadata_hash"]
                self._logger.info(f"{LC.DATASETMETADATA_INGESTION_COMPLETE.format(metadata_id=hash_sdmd, file_name=file_name)}")
                
                # Process file name
                file_name_prefix = self.utils.check_filename(file_name)
                file_name_original = file_name.replace(f"{file_name_prefix}_", "", 1)
                row_id = str(uuid.uuid4())
                
                # Process data sheets first (without layout)
                for sheet_name in df_excel_file.sheet_names:
                    if (sheet_name not in SdohConstants.NON_DATA_SHEET_LIST):  
                        sheet_data = df_excel_file.parse(sheet_name, dtype=str)
                        # Disable Arrow optimization to prevent BufferHolder overflow (SPARK-44979)
                        _arrow_conf = "spark.sql.execution.arrow.pyspark.enabled"
                        _prev_arrow = self.spark.conf.get(_arrow_conf, "false")
                        try:
                            self.spark.conf.set(_arrow_conf, "false")
                            spark_df = self.spark.createDataFrame(sheet_data)
                        finally:
                            self.spark.conf.set(_arrow_conf, _prev_arrow)
                        
                        # Create a JSON string for each row
                        json_df = self._process_dataset_in_chunks(spark_df, file_name, sheet_name)
                        
                        # Create a new DataFrame with the JSON string and other columns (WITHOUT layout)
                        current_timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
                        row_id = f"{sheet_name}_{current_timestamp}_{str(uuid.uuid4())}"
                        sheet_file_name = os.path.splitext(file_name_original)[0]
                        sheet_file_name = f"{sheet_file_name}_{sheet_name}_{hash_sdmd}"
                        data_df = json_df.withColumn("id", lit(row_id)) \
                                        .withColumn("datasetName", lit(file_name_original)) \
                                        .withColumn("datasetMetadataId", lit(hash_sdmd)) \
                                        .withColumn("datasetMetadata", lit(metadata_result["metadata_json"])) \
                                        .withColumn("datasetLayout", lit(None)) \
                                        .withColumn("createdDatetime", lit(datetime.now()))
                        
                        # Select the required columns
                        final_df = data_df.select("id", "datasetName", "datasetRowContent", "datasetMetadata", "datasetLayout", "createdDatetime")
                        
                        # Write to Delta table
                        final_df.write.format(SdohConstants.FORMAT_DELTA).mode(
                            SdohConstants.MODE_APPEND).save(f"{self.bronze_tables_path}/SdohDatasets")
                        self._collect_source_and_target_metrics_fn(metrics={"numSourceRecords": json_df.count()}, delta_table_path=f"{self.bronze_tables_path}/SdohDatasets")
                
                # Now process layout data once, outside the sheet loop
                layout_df = df_excel_file.parse(SdohConstants.SHEETNAME_LAYOUT)
                
                # Use existing _ingest_layout method to process layout
                layout_json_df = self._ingest_layout(layout_df, hash_sdmd)
                
                # Get all rows from the Delta table that need layout data
                existing_rows_df = self.spark.sql(f"""
                    SELECT id, datasetName, datasetRowContent, datasetMetadata, createdDatetime
                    FROM delta.`{self.bronze_tables_path}/SdohDatasets`
                    WHERE from_json(datasetMetadata, 'ARRAY<STRUCT<DataSetMetadataId: STRING>>')[0].DataSetMetadataId = '{hash_sdmd}' 
                    AND datasetName = '{file_name_original}'
                """)
                
                # Get row counts for both datasets
                content_row_count = existing_rows_df.count()
                layout_row_count = layout_json_df.count()
                
                # Add row number to content DataFrame
                content_with_row = existing_rows_df.withColumn(
                    "row_num", 
                    row_number().over(Window.orderBy(lit(1)))
                )
                
                # Add row number to layout DataFrame
                layout_with_row = layout_json_df.withColumn(
                    "row_num", 
                    row_number().over(Window.orderBy(lit(1)))
                )
                
                # Create a join condition that handles row mismatches with NULL values
                if content_row_count >= layout_row_count:
                    self._logger.info(f"Content rows ({content_row_count}) >= layout rows ({layout_row_count}). Adding NULL layout values to extra content rows.")
                    # Join will keep all content rows, with layout data where available
                    updated_rows = content_with_row.join(
                        layout_with_row,
                        content_with_row["row_num"] == layout_with_row["row_num"],
                        "left_outer"
                    )
                else:
                    self._logger.info(f"Layout rows ({layout_row_count}) > content rows ({content_row_count}). Creating additional rows for excess layout data.")
                    
                    # Create empty template rows to hold excess layout data
                    schema = existing_rows_df.schema
                    empty_rdd = self.spark.sparkContext.emptyRDD()
                    template_df = self.spark.createDataFrame(empty_rdd, schema)
                    
                    # Add enough empty rows to match layout row count
                    empty_rows_needed = layout_row_count - content_row_count
                    empty_rows = []
                    
                    for i in range(empty_rows_needed):
                        empty_row = {field.name: None for field in schema.fields}
                        # Only set fields that are actually in the schema
                        empty_row["datasetName"] = file_name_original
                        empty_row["id"] = row_id
                        # Add proper metadata JSON in the datasetMetadata field
                        empty_row["datasetMetadata"] = metadata_result["metadata_json"]
                        empty_row["datasetRowContent"] = "{}"  # Empty JSON content
                        empty_row["createdDatetime"] = datetime.now()
                        empty_rows.append(Row(**empty_row))
                    
                    if empty_rows:
                        # Create DataFrame from empty rows and add row numbers
                        empty_df = self.spark.createDataFrame(empty_rows, schema)
                        extra_content_rows = empty_df.withColumn(
                            "row_num", 
                            row_number().over(Window.orderBy(lit(1))) + lit(content_row_count)
                        )
                        
                        # Combine existing content rows with empty template rows
                        combined_content = content_with_row.unionAll(extra_content_rows)
                        
                        # Join with layout data
                        updated_rows = combined_content.join(
                            layout_with_row,
                            combined_content["row_num"] == layout_with_row["row_num"],
                            "left_outer"
                        )
                    else:
                        # If no extra rows needed (should never happen in this branch)
                        updated_rows = content_with_row.join(
                            layout_with_row,
                            content_with_row["row_num"] == layout_with_row["row_num"],
                            "left_outer"
                        )
                
                # Drop the row number columns and prepare for writing back
                updated_rows = updated_rows.drop(content_with_row["row_num"]).drop(layout_with_row["row_num"])
                
                # After the join, make sure to handle the selection correctly
                updated_rows = updated_rows.select(
                    content_with_row["id"],
                    content_with_row["datasetName"],
                    content_with_row["datasetRowContent"],
                    content_with_row["datasetMetadata"],
                    layout_with_row["datasetLayout"],
                    content_with_row["createdDatetime"]
                )
                
                # Write the updated rows back to the Delta table
                updated_rows.write.format(SdohConstants.FORMAT_DELTA).mode(
                    SdohConstants.MODE_OVERWRITE
                ).option(
                    "replaceWhere", 
                    f"from_json(datasetMetadata, 'ARRAY<STRUCT<DataSetMetadataId: STRING>>')[0].DataSetMetadataId = '{hash_sdmd}' " +
                    f"AND datasetName = '{file_name_original}'"
                ).save(f"{self.bronze_tables_path}/SdohDatasets")
                
                self._logger.info(f"{LC.DATASET_INGESTION_COMPLETE.format(dataset_name=file_name)}")
                list_processed_files.append(row.path)
                
            except Exception as ex:
                bool_excel_ingested = False
                exception_message = f"{LC.DATASET_INGESTION_FAILURE.format(dataset_name=datasetName, error_message=str(ex))}"
                self._logger.error(exception_message)
                message = f"{LC.MOVE_FAILED_FILES_FAILED_FOLDER}"
                self._logger.error(message)
                
                if self.ingest_exception_excel:
                    if isinstance(self.ingest_exception_excel.get('sourceFilePath'), Path):
                        self.ingest_exception_excel['sourceFilePath'] = str(self.ingest_exception_excel['sourceFilePath'])
                    self.exceptions.append(self.ingest_exception_excel)
                else:
                    self._logger.warning(f"No ingest_exception_excel context available for exception: {str(ex)}")
                    fallback_row = self.business_events_ingestion_service.create_new_business_event_row(
                        id=str(uuid.uuid4()), activityName=GlobalConstants.SDOH_BRONZE_INGESTION_ACTIVITY_NOTEBOOK,
                        targetFilePath=self.bronze_tables_path, targetLakehouseName=self.target_lakehouse_name,
                        targetTableName=GlobalConstants.SDOH_BRONZE_TABLE_NAME,
                        sourceFilePath=str(rowPath), sourceLakehouseName=self.source_lakehouse_name,
                        severity=GlobalConstants.ERROR,
                        eventType=GlobalConstants.SDOH_DELTA_TABLE_CREATION_FROM_PROCESS_FOLDER,
                        message=exception_message, exception=str(ex), active=True)
                    self.exceptions.append(fallback_row)
                self.utils._move_folder_to_failed_folder(self.utils.get_directory(row.path), self.sdoh_failed_folder_path, self.mssparkutils_client)
        
        return bool_excel_ingested

    def ingest_csv(self, df, timestamp, list_processed_files) -> bool:
        """
        Ingests a CSV file into the system.

        Args:
        - df (DataFrame): The DataFrame containing the data to be ingested.
        - timestamp (str): Timestamp of the ingestion which is prefixed to the file.
        - list_processed_files (list): List of processed files.

        Returns:
            bool: True if all files successfully ingested, False otherwise.
        """
        bool_csv_ingested = True
        csv_datasets = {}
        # Validate path and Group CSV files as per the dataset
        for datafile in df.rdd.toLocalIterator():
            rowPath = Path(datafile["path"])
            datasetname = rowPath.parent.name
            if (datasetname in csv_datasets.keys()):
                continue
            csv_datasets[datasetname] = df.filter(df.path.contains("/" + datasetname + "/"))

        for datasetName, dataset in csv_datasets.items():
            datasetFolder = self.utils.get_directory(dataset.first().path)
            try:
                self._logger.info(f"{LC.DATASET_INGESTION_START.format(dataset_name=datasetName)}")
                # Validate the CSV Dataset
                dataset.cache()
                validationError = self.bronze_validator.validate_csv_dataset(datasetFolder,
                                                                             timestamp,
                                                                             self.mssparkutils_client)
                if validationError is not None:
                    new_row = self.business_events_ingestion_service.create_new_business_event_row(id=str(uuid.uuid4()), activityName=GlobalConstants.SDOH_BRONZE_INGESTION_ACTIVITY_NOTEBOOK, 
                        targetFilePath= self.bronze_tables_path, targetLakehouseName= self.target_lakehouse_name, targetTableName=GlobalConstants.SDOH_BRONZE_TABLE_NAME,
                        sourceFilePath= datasetFolder, sourceLakehouseName= self.source_lakehouse_name, severity= GlobalConstants.ERROR, 
                        eventType= GlobalConstants.SDOH_VALIDATE_CSV_DATASET_FOR_REQUIRED_SHEETS_AND_COLUMNS, message= validationError, exception= validationError, active=True)
                    self.ingest_exception_csv = new_row
                    raise Exception(validationError)

                # Get necessary files
                metadata_file = dataset.filter(dataset.path.contains(SdohConstants.SHEETNAME_METADATA)).first()
                loc_conf_file = dataset.filter(dataset.path.contains(SdohConstants.SHEETNAME_LOCCONFIG)).first()
                layout_file = dataset.filter(dataset.path.contains(SdohConstants.SHEETNAME_LAYOUT)).first()
                data_df = dataset.filter(~dataset.path.contains(SdohConstants.SHEETNAME_LAYOUT)
                                    & ~dataset.path.contains(SdohConstants.SHEETNAME_METADATA)
                                    & ~dataset.path.contains(SdohConstants.SHEETNAME_LOCCONFIG))

                # Parse necessary files
                metadata_df = self.utils.read_csv_stream(bytes(metadata_file.content), metadata_file.path)
                loc_conf_df = self.utils.read_csv_stream(bytes(loc_conf_file.content), loc_conf_file.path)
                layout_df = self.utils.read_csv_stream(bytes(layout_file.content), layout_file.path)

                # Validate each file
                if not self.bronze_validator.validate_metadata_df(metadata_df):
                    exception_message = f"{LC.INVALID_METADATA_INFORMATION.format(file_path=metadata_file.path)}"
                    new_row = self.business_events_ingestion_service.create_new_business_event_row(id=str(uuid.uuid4()), activityName=GlobalConstants.SDOH_BRONZE_INGESTION_ACTIVITY_NOTEBOOK, 
                        targetFilePath= self.bronze_tables_path, targetLakehouseName= self.target_lakehouse_name, targetTableName=GlobalConstants.SDOH_BRONZE_TABLE_NAME,
                        sourceFilePath= datasetFolder, sourceLakehouseName= self.source_lakehouse_name, severity= GlobalConstants.ERROR, 
                        eventType= GlobalConstants.SDOH_VALIDATE_METADATA_DATAFRAME, message= exception_message, exception= exception_message, active=True)
                    self.ingest_exception_csv = new_row
                    raise Exception(exception_message)
                if not self.bronze_validator.validate_loc_conf_df(loc_conf_df):
                    message = f"{LC.INVALID_LOC_CONFIG_INFORMATION.format(file_path=loc_conf_file.path)}"
                    new_row = self.business_events_ingestion_service.create_new_business_event_row(id=str(uuid.uuid4()), activityName=GlobalConstants.SDOH_BRONZE_INGESTION_ACTIVITY_NOTEBOOK, 
                        targetFilePath= self.bronze_tables_path, targetLakehouseName= self.target_lakehouse_name, targetTableName=GlobalConstants.SDOH_BRONZE_TABLE_NAME,
                        sourceFilePath= datasetFolder, sourceLakehouseName= self.source_lakehouse_name, severity= GlobalConstants.ERROR, 
                        eventType= GlobalConstants.SDOH_VALIDATE_LOCATION_CONFIGURATION_DATAFRAME, message= message, exception= message, active=True)
                    self.ingest_exception_csv = new_row
                    raise Exception(message)
                if not self.bronze_validator.validate_layout_df(layout_df):
                    message = f"{LC.INVALID_LAYOUT_INFORMATION.format(file_path=layout_file.path)}"
                    new_row = self.business_events_ingestion_service.create_new_business_event_row(id=str(uuid.uuid4()), activityName=GlobalConstants.SDOH_BRONZE_INGESTION_ACTIVITY_NOTEBOOK, 
                        targetFilePath= self.bronze_tables_path, targetLakehouseName= self.target_lakehouse_name, targetTableName=GlobalConstants.SDOH_BRONZE_TABLE_NAME,
                        sourceFilePath= datasetFolder, sourceLakehouseName= self.source_lakehouse_name, severity= GlobalConstants.ERROR, 
                        eventType= GlobalConstants.SDOH_VALIDFATE_LAYOUT_DATAFRAME, message= message, exception= message, active=True)
                    self.ingest_exception_csv = new_row
                    raise Exception(message)

                # Process metadata
                metadata_df[SdohConstants.PUBLISHED_DATE] = pandas.to_datetime(metadata_df[SdohConstants.PUBLISHED_DATE])
                metadata_df[SdohConstants.VALIDITY_DATE] = pandas.to_datetime(metadata_df[SdohConstants.VALIDITY_DATE])
                loc_columns = self.utils.get_locationColumns(loc_conf_df)
                loc_conf = self.utils.prepare_location_configuration(loc_conf_df)
                metadata_result = self._ingest_metadata(metadata_df, loc_conf, metadata_file.path)
                hash_sdmd = metadata_result["metadata_hash"]
                list_processed_files.append(metadata_file.path)
                list_processed_files.append(loc_conf_file.path)
                self._logger.info(
                    f"{LC.DATASETMETADATA_INGESTION_COMPLETE.format(metadata_id=hash_sdmd, file_name=metadata_file.path)}"
                )

                # Process layout once - outside the data processing loop
                layout_json_df = self._ingest_layout(layout_df, hash_sdmd)
                list_processed_files.append(layout_file.path)
                
                # Process all data files first (without layout)
                all_data_rows = []
                
                for row in data_df.collect():
                    file_name = os.path.basename(row.path)
                    file_name_prefix = self.utils.check_filename(file_name)
                    file_name_original = file_name.replace(f"{file_name_prefix}_", "", 1)
                    csv_df = self.utils.read_csv_stream(bytes(row.content), row.path)
                    # Disable Arrow optimization to prevent BufferHolder overflow (SPARK-44979)
                    _arrow_conf = "spark.sql.execution.arrow.pyspark.enabled"
                    _prev_arrow = self.spark.conf.get(_arrow_conf, "false")
                    try:
                        self.spark.conf.set(_arrow_conf, "false")
                        spark_df = self.spark.createDataFrame(csv_df)
                    finally:
                        self.spark.conf.set(_arrow_conf, _prev_arrow)
                    # Create a JSON string for each row with chunking
                    json_df = self._process_dataset_in_chunks(spark_df, file_name)       
                    
                    # Create a new DataFrame with the JSON string and other columns (without layout)
                    current_timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
                    sheet_name = os.path.splitext(file_name_original)[0]
                    row_id = f"{sheet_name}_{current_timestamp}_{str(uuid.uuid4())}"
                    data_df_with_meta = json_df.withColumn("id", lit(row_id)) \
                                    .withColumn("datasetName", lit(file_name_original)) \
                                    .withColumn("datasetMetadata", lit(metadata_result["metadata_json"])) \
                                    .withColumn("datasetLayout", lit(None)) \
                                    .withColumn("createdDatetime", lit(datetime.now()))
                    
                    # Write to Delta table
                    data_df_with_meta.select("id", "datasetName", "datasetRowContent", "datasetMetadata", "datasetLayout", "createdDatetime") \
                        .write.format(SdohConstants.FORMAT_DELTA).mode(SdohConstants.MODE_APPEND) \
                        .save(f"{self.bronze_tables_path}/SdohDatasets")
                    
                    self._collect_source_and_target_metrics_fn(metrics={"numSourceRecords": json_df.count()}, delta_table_path=f"{self.bronze_tables_path}/SdohDatasets")
                    list_processed_files.append(row.path)
                
                # Get all rows from the Delta table that need layout data
                existing_rows_df = self.spark.sql(f"""
                    SELECT id, datasetName, datasetRowContent, datasetMetadata, createdDatetime
                    FROM delta.`{self.bronze_tables_path}/SdohDatasets`
                    WHERE from_json(datasetMetadata, 'ARRAY<STRUCT<DataSetMetadataId: STRING>>')[0].DataSetMetadataId = '{hash_sdmd}' 
                    AND datasetName LIKE '{file_name_original}%'
                """)
                
                # Get row counts for both datasets
                content_row_count = existing_rows_df.count()
                layout_row_count = layout_json_df.count()
                
                # Add row number to content DataFrame
                content_with_row = existing_rows_df.withColumn(
                    "row_num", 
                    row_number().over(Window.orderBy(lit(1)))
                )
                
                # Add row number to layout DataFrame
                layout_with_row = layout_json_df.withColumn(
                    "row_num", 
                    row_number().over(Window.orderBy(lit(1)))
                )
                
                # Create a join condition that handles row mismatches with NULL values
                if content_row_count >= layout_row_count:
                    self._logger.info(f"Content rows ({content_row_count}) >= layout rows ({layout_row_count}). Adding NULL layout values to extra content rows.")
                    # Join will keep all content rows, with layout data where available
                    updated_rows = content_with_row.join(
                        layout_with_row,
                        content_with_row["row_num"] == layout_with_row["row_num"],
                        "left_outer"
                    )
                else:
                    self._logger.info(f"Layout rows ({layout_row_count}) > content rows ({content_row_count}). Creating additional rows for excess layout data.")
                    
                    # Create empty template rows to hold excess layout data
                    schema = existing_rows_df.schema
                    empty_rdd = self.spark.sparkContext.emptyRDD()
                    template_df = self.spark.createDataFrame(empty_rdd, schema)
                    
                    # Add enough empty rows to match layout row count
                    empty_rows_needed = layout_row_count - content_row_count
                    empty_rows = []
                    
                    for i in range(empty_rows_needed):
                        empty_row = {field.name: None for field in schema.fields}
                        # Only set fields that are actually in the schema
                        empty_row["datasetName"] = file_name_original
                        empty_row["id"] = str(uuid.uuid4())
                        # Add proper metadata JSON in the datasetMetadata field
                        empty_row["datasetMetadata"] = metadata_result["metadata_json"]
                        empty_row["datasetRowContent"] = "{}"  # Empty JSON content
                        empty_row["createdDatetime"] = datetime.now()
                        empty_rows.append(Row(**empty_row))
                    
                    if empty_rows:
                        # Create DataFrame from empty rows and add row numbers
                        empty_df = self.spark.createDataFrame(empty_rows, schema)
                        extra_content_rows = empty_df.withColumn(
                            "row_num", 
                            row_number().over(Window.orderBy(lit(1))) + lit(content_row_count)
                        )
                        
                        # Combine existing content rows with empty template rows
                        combined_content = content_with_row.unionAll(extra_content_rows)
                        
                        # Join with layout data
                        updated_rows = combined_content.join(
                            layout_with_row,
                            combined_content["row_num"] == layout_with_row["row_num"],
                            "left_outer"
                        )
                    else:
                        # If no extra rows needed (should never happen in this branch)
                        updated_rows = content_with_row.join(
                            layout_with_row,
                            content_with_row["row_num"] == layout_with_row["row_num"],
                            "left_outer"
                        )
                
                # Drop the row number columns and prepare for writing back
                updated_rows = updated_rows.drop(content_with_row["row_num"]).drop(layout_with_row["row_num"])
                
                # After the join, make sure to handle the selection correctly
                updated_rows = updated_rows.select(
                    content_with_row["id"],
                    content_with_row["datasetName"],
                    content_with_row["datasetRowContent"],
                    content_with_row["datasetMetadata"],
                    layout_with_row["datasetLayout"],
                    content_with_row["createdDatetime"]
                )
                
                # Write the updated rows back to the Delta table
                updated_rows.write.format(SdohConstants.FORMAT_DELTA).mode(
                    SdohConstants.MODE_OVERWRITE
                ).option(
                    "replaceWhere", 
                    f"from_json(datasetMetadata, 'ARRAY<STRUCT<DataSetMetadataId: STRING>>')[0].DataSetMetadataId = '{hash_sdmd}' " +
                    f"AND datasetName LIKE '{file_name_original}%'"
                ).save(f"{self.bronze_tables_path}/SdohDatasets")

                self._logger.info(f"{LC.DATASET_INGESTION_COMPLETE.format(dataset_name=datasetName)}")
                
            except Exception as ex:
                bool_csv_ingested = False
                exception_message = f"{LC.DATASET_INGESTION_FAILURE.format(dataset_name=datasetName, error_message=str(ex))}"
                self._logger.error(exception_message)
                message = f"{LC.MOVE_FAILED_FILES_FAILED_FOLDER}"
                self._logger.error(message)
            
                self.exceptions.append(self.ingest_exception_csv)
                self.utils._move_folder_to_failed_folder(datasetFolder, self.sdoh_failed_folder_path, self.mssparkutils_client)
        
        return bool_csv_ingested

    def _ingest_metadata(self, metadata_df, loc_config, folder_path) -> str:
        """
        Ingest metadata table
        Args:
        - metadata_df - Metadata dataframe in dataset
        - loc_config - Prepared location configuration string
        - folder_path - str: Path for the dataset

        Returns:
        - Hash of the dataset metadata information
        """
        hash_sdmd = pandas.util.hash_pandas_object(metadata_df).astype(str)[0]

        metadata_df.insert(loc=len(metadata_df.columns),
                           column=SdohConstants.COLUMN_DATASET_METADATA_ID, value=hash_sdmd)
        metadata_df.insert(loc=len(metadata_df.columns),
                           column=GlobalConstants.DEFAULT_BRONZE_CREATED_DATE_COL, value=pandas.Timestamp(SdohConstants.NOW))
        metadata_df.insert(loc=len(metadata_df.columns),
                           column=SdohConstants.FOLDER_PATH, value=folder_path)
        metadata_df.insert(loc=len(metadata_df.columns),
                           column=SdohConstants.COLUMN_LOC_CONFIG, value=loc_config)
        
        # First convert datetime columns to string format to avoid NaT issues
        datetime_cols = metadata_df.select_dtypes(include=["datetime64[ns]"]).columns
        for col in datetime_cols:
            # Convert datetime to string but handle NaT values properly
            metadata_df[col] = metadata_df[col].dt.strftime('%Y-%m-%dT%H:%M:%S').fillna('')

        # Now convert all other columns to string type and fill nulls
        for col in metadata_df.columns:
            if col not in datetime_cols:
                metadata_df[col] = metadata_df[col].astype(str).fillna('')

        # Define explicit schema for the DataFrame
        schema = StructType([
            StructField(col, StringType(), True) for col in metadata_df.columns
        ])
        
        # Create Spark DataFrame with explicit schema
        spark_df = self.spark.createDataFrame(metadata_df.values.tolist(), schema=schema)
        
        for col_name in spark_df.columns:
            spark_df=spark_df.withColumnRenamed(col_name,col_name.strip())
            
        datetime_cols = metadata_df.select_dtypes(include=["datetime64[ns]"]).columns
        for col in datetime_cols:
            metadata_df[col] = metadata_df[col].dt.strftime('%Y-%m-%dT%H:%M:%S')
        
        metadata_json = metadata_df.to_json(orient="records")        
        return {"metadata_hash": hash_sdmd, "metadata_json": metadata_json}

    def _ingest_layout(self, layout_df, hash_sdmd) -> None:
        """
        Ingest layout table as individual row JSON strings
        
        Args:
            layout_df - Layout dataframe in dataset
            hash_sdmd - Hash of the dataset metadata information
            
        Returns:
            DataFrame with one row per layout entry, each containing a JSON string
        """
        # Add required columns
        layout_df.insert(loc=len(layout_df.columns),
                         column=SdohConstants.COLUMN_DATASET_METADATA_ID, value=hash_sdmd)
        layout_df.insert(loc=len(layout_df.columns), 
                         column=GlobalConstants.DEFAULT_BRONZE_CREATED_DATE_COL,
                         value=pandas.Timestamp(SdohConstants.NOW))
        hash_layout = pandas.util.hash_pandas_object(layout_df).astype(str)
        layout_df.insert(loc=len(layout_df.columns),
                         column=SdohConstants.COLUMN_LAYOUT_ID, value=hash_layout)
        
        # Convert to Spark DataFrame and clean column names
        spark_df = self.spark.createDataFrame(layout_df)
        for col_name in spark_df.columns:
            spark_df = spark_df.withColumnRenamed(col_name, col_name.strip())

        # Process each row as a separate JSON string
        layout_json_df = spark_df.withColumn(
            "datasetLayout", 
            to_json(struct(*[col(c) for c in spark_df.columns]))
        ).select("datasetLayout")
        
        return layout_json_df

    def _process_dataset_in_chunks(self, spark_df, file_name, sheet_name=None):
        """
        Processes large datasets by splitting columns into smaller chunks
        and creating JSON strings with row identification
        
        Args:
            spark_df: The original dataframe with all columns
            file_name: Name of the dataset file
            sheet_name: Name of the sheet (for Excel files)
            
        Returns:
            DataFrame with datasetRowContent containing JSON data
        """
        # Special handling for LocationAffordabilityIndex

        # Set column chunk size based on dataset
        MAX_COLUMNS_PER_CHUNK = 100
        total_columns = len(spark_df.columns)
        
        # Add a unique row identifier
        spark_df = spark_df.withColumn("row_id", monotonically_increasing_id())
        
        # Only chunk if we have more columns than our threshold
        if total_columns > MAX_COLUMNS_PER_CHUNK:
            self._logger.info(f"Processing large dataset {file_name} with {total_columns} columns in chunks")
            
            # Calculate how many chunks we need
            num_chunks = (total_columns + MAX_COLUMNS_PER_CHUNK - 1) // MAX_COLUMNS_PER_CHUNK
            
            # Process in column chunks
            chunk_dfs = []
            for chunk_idx in range(num_chunks):
                start_idx = chunk_idx * MAX_COLUMNS_PER_CHUNK
                end_idx = min((chunk_idx + 1) * MAX_COLUMNS_PER_CHUNK, total_columns)
                
                # Get columns for this chunk
                chunk_columns = spark_df.columns[start_idx:end_idx]
                
                # Ensure row_id is included if not already in this chunk
                if "row_id" not in chunk_columns:
                    chunk_columns = ["row_id"] + [c for c in chunk_columns if c != "row_id"]
                    
                self._logger.info(f"Processing chunk {chunk_idx+1}/{num_chunks} with {len(chunk_columns)} columns")
                
                # Create JSON string for this chunk (include row_id)
                chunk_df = spark_df.select(chunk_columns).withColumn(
                    "datasetRowContent", 
                    to_json(struct(*[col(c) for c in chunk_columns]))
                ).select("datasetRowContent")
                
                chunk_dfs.append(chunk_df)
            
            # Union all chunks
            if len(chunk_dfs) > 1:
                result_df = reduce(DataFrame.unionAll, chunk_dfs)
                return result_df
            else:
                return chunk_dfs[0]
        else:
            # For smaller datasets, process all columns at once with row ID
            return spark_df.withColumn(
                "datasetRowContent", 
                to_json(struct(*[col(c) for c in spark_df.columns]))
            ).select("datasetRowContent")