# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
"""
Module defining logging constants
"""

# pylint: disable=R0903 # too-few-public-methods
# pylint: disable=C0301 # line-too-long


class LoggingConstants:
    """Logging constants"""

    NULL_ARGUMENT_ERR_MSG = "{argument_name} cannot be empty. Please set a value."
    TABLE_EXISTS = "{table_name} exists in {lakehouse}"
    STREAMING_PATH_DOES_NOT_EXIST_INFO_MSG = "Streaming path {streaming_path} does not exist. Skipping streaming on this path."

    # Invalid arguments
    INVALID_ARGUMENT = "Invalid Argument."
    BRONZE_SOURCE_PATH_PATTERN_MUST_CONTAIN_SUBSTRING = "source_path_pattern must contain the substring <resource_name>."

    # Flattening logging messages
    INVALID_CONFIG_FORMAT_ERR_MSG = "Invalid configuration format. Should be [{{\"resourceType\":\"Patient\",\"path\":\"ndjson file path\"}}] but instead is:"
    MISSING_CONFIGURATION_ERR_MSG = "Can't find configuration for resource_type"
    FLATTENING_ALL_RESOURCES_START_INFO_MSG = "Flattening all resources started"
    FLATTENING_ALL_RESOURCES_END_INFO_MSG = "Flattening all resources completed"
    FLATTENING_RESOURCE_START_INFO_MSG = "Flattening started for resource:"
    FLATTENING_RESOURCE_END_INFO_MSG = "Flattening completed for resource:"
    FLATTENING_NONE_DATAFRAME = "A None dataframe was passed for {resource} resource. Creating an empty dataframe with given schema in config and continue to process the resulting dataframe."
    FLATTENING_RESOURCE_ERR_MSG = "Error occurred while flattening resource"
    SAVING_FLATTENED_RESOURCE_START_INFO_MSG = "Saving flattened resource:"
    SAVING_FLATTENED_RESOURCE_END_INFO_MSG = "Successfully saved flattened resource:"
    SAVING_FLATTENED_RESOURCE_ERR_MSG = "Error occurred while saving flattened resource:"
    UNSUPPORTED_RESOURCE_STATUS_DETAILS = "Resource type validation unsuccessful: {0} is not supported."
    SUPPORTED_RESOURCE_STATUS_DETAILS = "Resource type validation successful: {0} is supported."
    FLATTENING_INVALID_COLUMN_CONFIGURATION = "Resource {resource_type} column configuration path is invalid: {config_path}. Generating column config from schema: {ex_message}"
    FLATTENING_LOADING_CONFIGURATION_AT_PATH = "Loading column config at: {config_path} for resource: {resource_type}"
    FLATTENING_GENERATING_CONFIGURATION = "Column configuration path is not defined. Generating column config from schema for: {resource_type}"
    FLATTENING_EMPTY_CONFIG_FILE = "No entities in config file: {config_path} to flatten."
    FLATTENING_SOURCE_RESOURCES_WITH_NO_DATA = "{resources_with_no_source_data} have no data in bronze. Flatten using empty dataframes."

    # validation logging messages
    CREATING_BUSINESS_EVENTS_TABLE_INFO_MSG = "Business Events Table does not exist. Creating business events table at {delta_table_path}"
    READING_VALIDATION_CONFIG_INFO_MSG = "Reading validation config from {validation_config_path}"
    VALIDATION_CONFIG_DOES_NOT_EXIST_MSG = "Validation config at {validation_config_path} does not exist"
    LOADING_BUSINESS_EVENTS_SCHEMA_INFO_MSG = "Loading business events schema from {business_events_schema_path}"
    COMPRESSING_AND_MOVING_FAILED_FILES_INFO_MSG = "Compressing and moving failed files to {failed_folder_path}"
    NO_VALIDATION_RULES_MSG = "No validation rules were found. Skipping Validation."

    # creating empty tables logging messages
    CREATING_TABLE_START_INFO_MSG = "Creating delta table for resource:"
    CREATING_TABLE_ERR_MSG = "Error occurred while creating delta table for resource:"
    SCHEMA_NOT_FOUND_ERR_MSG = "Avro schema not found for this resource"
    CREATING_TABLE_END_INFO_MSG = "Successfully created delta table for resource:"
    CREATING_TABLE_SKIPPED_INFO_MSG = "Skipping creating delta table, as it already exists for resource:"
    CREATING_EMPTY_SILVER_TABLES_ERR_MSG = "Error occurred while creating empty silver tables: {exception_details}"
    CREATE_SILVER_TABLES_INFO_MSG = "Creating silver tables for resources in config."
    CREATE_SILVER_TABLES_ERR_MSG = "Failed to create silver tables. Exception details: {exception_details}"

    CREATING_EMPTY_TABLES_ERR_MSG = "Error occurred while creating empty tables in {lakehouse}. Exception Details: {exception_details}"

    # utils append_unique_to_delta_managed logging messages
    CREATING_AND_FINDING_DATABASE_ERR_MSG = "Unable to find and create delta table"
    EMPTY_UNIQUE_COLUMNS_INPUT_ERR_MSG = "Invalid 'unique_columns' input. Unique columns cannot be empty."

    # NLPService logging messages
    INVALID_BATCHING_INPUT_DF_ERR_MSG = "Batching the input dataframe failed. 'input_df', must be a DataFrame"
    INVALID_BATCHING_INPUT_BATCH_SIZE_ERR_MSG = "Batching the input dataframe failed. 'batch_size' must be a positive integer"
    #FINAL_BATCHED_DATAFRAME_INFO_MSG = "NLP service batched the input dataframe. Batched dataframe has a count of:"
    INVALID_REPARTITION_INPUT_DF_ERR_MSG = "Repartitioning the input dataframe failed. 'input_df', must be a DataFrame"
    FINAL_REPARTITION_INFO_MSG = "Batched dataframe has been repartitioned to have partition/s:"
    ANALYZED_DATAFRAME_REORDERING_INFO_MSG = "The analyzed dataframe count after exploding during reordering:"
    FINAL_REORDER_ANALYZED_DATAFRAME_INFO_MSG = "Reordered/final text analysis results dataframe has a count of:"
    #FINAL_ANALYZED_DATAFRAME_INFO_MSG = "NLP service analyzed dataframe has a count of:"
   

    # Flatten Manager
    FLATTEN_MANAGER_CREATE_FLATTEN_TABLES_STARTED_INFO_MSG = "Flatten manager create flatten tables started."
    FLATTEN_MANAGER_CREATE_FLATTEN_TABLES_COMPLETED_INFO_MSG = "Flatten manager create flatten tables completed."

    # fhirtoomop logging messages
    OMOP_INGESTION_START_INFO_MSG = 'OMOP ingestion started.'
    OMOP_INGESTION_COMPLETED_INFO_MSG = 'OMOP ingestion completed.'
    MAIN_ORCH_CHECK_DB_INFO_MSG = "Database `{0}` verified at '{1}'."
    BEGAN_EXECUTION_INFO_MSG = "Began execution"
    COMPLETED_EXECUTION_INFO_MSG = "Completed execution"
    STREAMING_FAILED_ERROR_MSG = "Streaming failed with exception: {0}"
    MAIN_ORCH_NO_FILES_FOUND_DEBUG_MSG = "No files to process for FHIR to OMOP transformation. Please ensure files to process are located in {0}."
    MAIN_ORCH_OBTAIN_FILE_LOCK_INFO_MSG = "Document {0} obtained from {1}."
    MAIN_ORCH_SUCCESS_TRANSFORMATION_INFO_MSG = "Successfully transformed file: {0}."
    MAIN_ORCH_FLATTENING_FAILURE_ERROR_MSG = "Flattening failed. Returned with status: {0}."
    MAIN_ORCH_FLATTENING_QUALIFIED_INFO_MSG = "Flatten qualified to run."
    MAIN_ORCH_FLATTENING_UNQUALIFIED_INFO_MSG = "Flatten did not qualify to run."
    MAIN_ORCH_DTT_QUALIFIED_INFO_MSG = "DTT qualified to run. Workflow invoked."
    MAIN_ORCH_DTT_UNQUALIFIED_INFO_MSG = "DTT did not qualify to run."
    DTT_TRANSFORMATION_EXCEPTION_ERROR_MSG = "DTT transformation failed. {0} raised. Details: {1}."
    OMOP_TRANSFORMATION_EXCEPTION_ERROR_MSG = "OMOP transformation failed. {0} raised. Details: {1}."
    OMOP_POSTPROCESS_DEDUPLICATION_ERROR_MSG = "OMOP postprocess was unable to deduplicate the {0} table."
    RMT_CREATED_CONCEPT_FILE = "Concept.json file was successfully created at: {0}."
    SUCCESSFULLY_MOUNTED_PATH = "Successfully mounted path: {0} at {1}"
    DTT_SUCCESS_INFO_MSG = "DTT workflow completed."
    RMT_SUCCESS_INFO_MSG = "RMT workflow completed."
    GENERIC_DTT_TRANSFORMATION_SUCCESS_MSG = "Generic DTT transformation completed successfully."
    MAIN_ORCH_GET_NEXT_MSG_INFO_MSG = "Began process to return the least recently returned file."
    DTT_APP_INSIGHTS_SET_INFO_MSG = "Set DTT application insights connection string in spark setting"
    IDM_TRANSFORMATION_EXCEPTION_ERROR_MSG = "IDM transformation failed. {0} raised. Details: {1}."
    SDOH_TRANSFORMATION_EXCEPTION_ERROR_MSG = "SDOH transformation failed. {0} raised. Details: {1}."

    # Drug_Era generation logging messages
    NORMALIZE_DRUG_EXPOSURE_START_INFO_MSG = "Normalizing drug exposure end dates for '{0}.{1}'."
    NORMALIZE_DRUG_EXPOSURE_END_INFO_MSG = "Succefully normalized '{0}.{1}' end dates and ingredient concept ids."
    GROUP_OVERLAPPING_EXPOSURES_START_INFO_MSG = "Grouping overlapping drug exposures."
    GROUP_OVERLAPPING_EXPOSURES_END_INFO_MSG = "Successfully grouped overlapping drug exposures."
    CALCULATE_FINAL_DRUG_ERAS_START_INFO_MSG = "Calculating final drug eras with gap days/persistence window."
    CALCULATE_FINAL_DRUG_ERAS_END_INFO_MSG = "Successfully calculated final drug eras with gap days/persistence window."
    GENERATE_DRUG_ERAS_START_INFO_MSG = "Generating '{0}.{1}' table."
    GENERATE_DRUG_ERAS_END_INFO_MSG = "Successfully generated and saved '{0}.{1}' table."
    DELETE_EXISTING_DRUG_ERAS_INFO_MSG = "Succesfully deleted existing drug_era table records."
    DRUG_ERA_TABLE_DOES_NOT_EXIST_INFO_MSG = "Drug era table does not exist. Creating new table '{0}.{1}'"
    GENERATE_DRUG_ERAS_SKIPPED_INFO_MSG = "Skipped drug era generation. No data to process."
    TABLE_OR_VIEW_NOT_FOUND_ERR_MSG = "Please ensure that the tables '{db}.drug_exposure', '{db}.concept_ancestor', and '{db}.concept' exist in the database. Failed in executing SQL query for retrieving drug exposure information."
    GENERATE_DRUG_ERAS_UNEXPECTED_ERR_MSG = "An unexpected error occurred while generating the drug era table"

    # Bronze ingestion service logging messages
    BRONZE_INGESTION_START_INFO_MSG = 'Bronze ingestion started.'
    BRONZE_INGEST_RSC_LIST_INFO_MSG = 'Bronze ingestion will stream on the following resources: {0}.'
    SET_STRUCTURED_STREAMING_INFO_MSG = 'Setting structured streaming on the following path: {0}'
    BRONZE_INGESTION_START_LOAD_INFO_MSG = 'Loading Schema at: {path}'
    BRONZE_INGESTION_END_LOAD_INFO_MSG = 'All resource schemas completed loading.'
    INGESTION_START_STREAM_INFO_MSG = 'Ingestion began streaming for path: {0}.'
    BRONZE_INGESTION_PATH_NOT_FOUND_INFO_MSG = 'Streaming path {path} does not exist. Create an empty table for {resource_name} if table does not exist.'
    STREAM_ORCHESTRATOR_END_QUERIES_INFO_MSG = 'All queries completed and streams terminated.'
    FILTERING_BRONZE_DF_ON_RESOURCE_TYPE_INFO_MSG = 'Filtering bronze source df where resourceType == {resource_name}'
    PATH_NOT_EXIST_ERR_MSG = "{process_name} process ended because the following path doesn't exist : {path}"
    MICRO_BATCH_APPEND_TO_DELTA_MANAGED_INFO_MSG = 'Bronze ingestion micro batch successfully completed: {{delta_table_path: "{delta_table_path}", records_persisted: {num_records_persisted}, validation_errors: {num_validation_errors}, batch id: {batch_id}}}'
    BRONZE_INGESTION_VALIDATION_ERROR_FAILURE_MSG = "The transformation encountered validation errors related to the files in the process folder. Files with errors have been moved to the failed folder. The individual errors can be found in the BusinessEvents table in the Admin lakehouse. Use the following query to identify the validation errors that were encountered: select * from BusinessEvents where runId = {run_id}"

    # SDOH Bronze ingestion service logging messages
    EMPTY_SOURCE_PATH = "No folders found in the provided source path: {source_path}."
    EMPTY_PROCESS_PATH = "No folders found in the provided process path: {process_path}."
    SDOH_BRONZE_INGESTION_PROCESS_NAME = "SDOH bronze ingestion"
    SDOH_INGESTION_STARTED = "SDOH ingestion started."
    SDOH_INGESTION_COMPLETED = "SDOH ingestion completed."
    INVALID_EXCEL_FILE_FORMAT = "Invalid file format for excel dataset: {file_path}."
    INVALID_DATASET_MISSING_METADATA = "Missing metadata information in dataset: {file_path}."
    INVALID_DATASET_MISSING_LAYOUT = "Missing layout information in dataset: {file_path}."
    INVALID_DATASET_MISSING_LOCATION_CONFIG = "Missing location configuration information in dataset: {file_path}."
    INVALID_DATASET_MISSING_DATA = "Missing data file in dataset: {file_path}."
    INVALID_LAYOUT_INFORMATION = "Invalid layout information in dataset: {file_path}."
    INVALID_METADATA_INFORMATION = "Invalid metadata information in dataset: {file_path}."
    INVALID_LOC_CONFIG_INFORMATION = "Invalid location configuration information in dataset: {file_path}."
    INVALID_DATAFILE_ONE_COLUMN = "Invalid data file, it has only one column. File Path: {file_path}"
    INVALID_DATAFILE_MISSING_LOCATION_COLUMN = "Invalid data file, missing location columns. File Path: {file_path}"
    INVALID_DATAFILE_MISSING_DATA_COLUMN = "Invalid data file, missing data columns. File Path: {file_path}"
    DATAFILE_TABLE_CREATION_ERROR = "Unable to create table for the data file in the dataset:{file_path}. Error:{error_message}"
    DATASETMETADATA_INGESTION_COMPLETE = "Metadata ingestion completed for metadata id {metadata_id} for dataset {file_name}."
    INGESTION_FAILURE = "Ingestion failed with error: {error_message}."
    CSV_READ_FAILURE = "Error reading the csv dataset. File:{file_path}. Error:{error_message}."
    EXCEL_READ_FAILURE = "Error reading the excel dataset. File:{file_path}. Error:{error_message}."
    INCORRECT_FILE_PATH = "Ingestion path for the file is incorrect: {file_name}.Expected path: '...\\Ingest\\SDOH\\<FileFormat>\\<PublisherName>\\<DatasetFolder>\\<FileName.FileFormat>'"
    METADATAID_ALREADY_EXISTS_LOC_UPDATE = "Metadata id already exists in DataSetMetadata table for metadata id {metadata_id}. Updating location configuration."
    LAYOUT_INGESTION_COMPLETE = "Layout ingestion completed for dataset {file_name}."
    DATASET_INGESTION_START = "Starting to ingest dataset: {dataset_name}."
    DATASET_INGESTION_COMPLETE = "Dataset successfully ingested {dataset_name}."
    DATASET_INGESTION_FAILURE = "Ingestion failed for the dataset:{dataset_name} with error: {error_message}."
    INVALID_DATASET = "Invalid dataset: {dataset_name}."
    DATA_TABLE_INGESTION_COMPLETE = "Data table ingestion completed for table {table_name}."
    ALL_DATA_TABLES_INGESTION_COMPLETE = "Ingestion completed for all tables from dataset {file_name}."
    SDOH_BRONZE_INGESTION_START_INFO_MSG = 'SDOH Bronze ingestion started.'
    SDOH_BRONZE_INGESTION_END_INFO_MSG = "SDOH Bronze ingestion completed."
    SDOH_INCORRECT_SOURCE_PATH_ERR_MSG = "Incorrect source path for SDOH Bronze ingestion.The Process folder path doesn't match the Unified folder structure."
    SDOH_BRONZE_DATASET_INGESTION_FALIURE = "SDOH Bronze Ingestion failed for one or more DataSets."
    RETRY_LIMIT_EXCEEDED = "Retry limit exceeded."
    SDOH_BRONZE_DATASET_INGESTION_FALIURE = "SDOH Bronze Ingestion failed for one or more DataSets."
    MOVE_FAILED_FILES_FAILED_FOLDER = "Initiating failed dataset transfer to failed folder."
    FILE_TRANSFER_PROCESS_FOLDER = "Starting the file transfer to the Process folder {process_folder}."
    PARTIAL_FILE_MOVEMENT_ERROR_MSG = "Error occurred while moving the file {file_path} to the failed folder. Error: {error}"

    SDOH_PROCESSED_FILES_INFO_MSG = "Total files processed: {total_files_processed}."

    # SDOH Silver ingestion service logging messages
    SDOH_TABLES_PROCESSING = "Processing table:{table_name}."
    SDOH_TABLES_PROCESSING_COMPLETED = "Completed processing table:{table_name}."
    SDOH_TABLES_DATASETMETADATAID_NOT_FOUND = "DataSetMetadataId is not available for table {table_name}"
    SDOH_TABLES_METADATA_DTT_MAPPING_PROCESSING = "Generating DTT mapping for SDOH metadata tables."
    SDOH_TABLES_METADATA_DTT_MAPPING_PROCESSED = "Completed generating DTT mapping for SDOH metadata tables."
    SDOH_TABLES_DATA_DTT_MAPPING_PROCESSING = "Generating DTT mapping."
    SDOH_TABLES_DATA_DTT_MAPPING_PROCESSED = "Completed the DTT mapping process."
    SDOH_TABLES_LOCATION_CONFIGURATION_NOT_FOUND = "Location configuration not found for table {table_name}."

    # Silver Ingestion Service logging messages
    LAKEHOUSE_DOES_NOT_EXIST = "The lakehouse with name {lakehouse_name} does not exist."
    SILVER_INGESTION_SINGLE_TABLE_START_INFO_MSG = 'Silver ingestion from a single table started.'
    SILVER_INGESTION_SINGLE_TABLE_COMPLETED_INFO_MSG = 'Silver ingestion from a single table completed.'
    SILVER_INGESTION_MULTIPLE_TABLES_START_INFO_MSG = 'Silver ingestion from multiple tables started.'
    SILVER_INGESTION_MULTIPLE_TABLES_COMPLETED_INFO_MSG = 'Silver ingestion from multiple tables completed.'
    SILVER_INGESTION_SOURCE_TABLE_DOES_NOT_EXIST_OR_EMPTY = "The source table at {source_table_path} either does not exist or is empty."
    SILVER_INGESTION_SOURCE_AND_TARGET_TABLES_DO_NOT_EXIST_OR_EMPTY = "The source table at {source_table_path} either does not exist or is empty and the target table {target_table_path} does not exist. Calling transformation function with None Dataframe."
    SILVER_INGESTION_SOURCE_TABLE_DOES_EXIST = "The source table at {table_path} does exist. Setting up structured streaming on the source table."
    SILVER_INGESTION_SETUP_TABLE_DOES_NOT_EXIST = "The target table at {table_path} does not exist. It has been marked for creation"
    SILVER_INGESTION_SETUP_TABLE_EVOLVED_SCHEMA = "Incoming schema has evolved. The target table at {table_path} has been marked for creation"
    SILVER_INGESTION_SETUP_TABLES_SKIPPED = "Silver tables setup skipped. All the tables are up to date."
    SILVER_INGESTION_TRANSFORMATION_SKIPPED = "Skipping streaming for resource {resource_name} from source table at {source_table_path}. No data for resource: {resource_name}"

    SILVER_INGESTION_START_STREAM_INFO_MSG = 'Began Silver Ingestion streaming : {{resource: "{resource}", source_table_path: "{source_table_path}"}}'
    SILVER_INGESTION_SET_MAX_BYTES_AND_FILES_PER_TRIGGER_INFO_MSG = 'Setting stream reader options: {{maxFilesPerTrigger: "{max_files_per_trigger}", maxBytesPerTrigger: "{max_bytes_per_trigger}"}}'
    SILVER_INGESTION_PARSING_DF_NO_CONFIG_FOUND_ERROR_MSG = 'Error while parsing dataframe : {{resource: "{resource}", config_path: "{config_path}", source_table_path: "{source_table_path}"}}'

    SILVER_INGESTION_FAILED_TO_LOAD_SCHEMA_ERROR_MSG = 'Failed to load schema : {{resource: "{resource}", config_path: "{config_path}"}}'
    SILVER_INGESTION_FAILED_TO_PARSE_RESOURCE_ERROR_MSG = 'Error occurred while parsing  dataframe : {{resource: "{resource}", exception_details: "{exception_details}"}}'
    SILVER_INGESTION_TRANSFORMATION_ERROR_MSG = 'Error occurred while ingesting data : {{resource: "{resource}", source_path: "{source_path}" , exception_details: "{exception_details}"}}'

    SILVER_INGESTION_SKIPPED_NO_RECORDS_INFO_MSG = 'No new records found, silver ingestion skipped : {{resource: "{resource}", source_table_path: "{source_table_path}"}}'
    SILVER_INGESTION_VALIDATE_CHECKPOINT_NO_DATA_MSG = "Delta table exists but is empty. Removing checkpoint metadata for {resource_name} before streaming."
    SILVER_INGESTION_VALIDATE_CHECKPOINT_NO_DELTA_TABLE_MSG = "Delta table does not exist. Removing checkpoint metadata for {resource_name} before streaming."
    SILVER_INGESTION_VALIDATE_CHECKPOINT_FAILED_ERROR_MSG = "Error while validating checkpoint for {resource_name} before streaming."
    SILVER_INGESTION_DELTA_TABLE_DETAILS_INCOMPLETE_WARNING_MSG = "Delta table details for {delta_table_path} are incomplete. numFiles or sizeInBytes is missing."
    SILVER_INGESTION_DELTA_TABLE_EMPTY_CHECK_ERROR_MSG = "Error while checking if Delta table is empty: {error_message}"
    SILVER_INGESTION_FAILED_TO_LOAD_RESOURCE_TYPES_ERROR_MSG = "Error while getting partition values for Delta table {delta_table_path}: {exception_details}"

    
    # Generic checkpoint validation logging messages
    GENERIC_VALIDATE_CHECKPOINT_NO_DATA_MSG = "Delta table exists but is empty. Removing checkpoint metadata for {resource_name} before streaming."
    GENERIC_VALIDATE_CHECKPOINT_NO_DELTA_TABLE_MSG = "Delta table does not exist. Removing checkpoint metadata for {resource_name} before streaming."
    GENERIC_VALIDATE_CHECKPOINT_FAILED_ERROR_MSG = "Error while validating checkpoint for {resource_name} before streaming."
    GENERIC_DELTA_TABLE_EMPTY_CHECK_ERROR_MSG = "Error while checking if Delta table is empty: {error_message}"

    # Dax Ingestion Services logging messages
    DAX_BRONZE_INGESTION_START_INFO_MSG = "Dax Bronze ingestion started."
    DAX_SILVER_INGESTION_START_INFO_MSG = "Dax Silver ingestion started."
    DAX_INGESTION_TRANSFORMATION_NO_SCHEMA = "Skipping dax silver transformation for source table at {source_table_path} and resource {resource_name}. There are no schema details available for this resource."
    DAX_INGESTION_FAILED_TO_PROCESS_GENERIC_RESOURCE_ERROR_MSG = "Failed to process generic resource {resource_name}. Error: {exception_details}"
    DAX_DATA_COLUMN_NOT_FOUND_ERROR = "Required column {column} not found in the source table"
    DAX_DATA_INPUT_SCHEMA_FORMAT_ERROR = "Invalid schema format for input json"
    DAX_DATA_OUTPUT_NONE_WARNING = "Failed to generate enrichment data"


    # Generic checkpoint validation logging messages
    GENERIC_VALIDATE_CHECKPOINT_NO_DATA_MSG = "Delta table exists but is empty. Removing checkpoint metadata for {resource_name} before streaming."
    GENERIC_VALIDATE_CHECKPOINT_NO_DELTA_TABLE_MSG = "Delta table does not exist. Removing checkpoint metadata for {resource_name} before streaming."
    GENERIC_VALIDATE_CHECKPOINT_FAILED_ERROR_MSG = "Error while validating checkpoint for {resource_name} before streaming."
    GENERIC_DELTA_TABLE_EMPTY_CHECK_ERROR_MSG = "Error while checking if Delta table is empty: {error_message}"

    # Normalization error message
    REFERENCE_NORMALIZATION_INFO_MSG = "Skipping {column}.{nested_ref_name} reference normalization. Unsupported schema: {schema}. "
    REFERENCE_NORMALIZATION_ERR_MSG = "Reference normalization error when processing data column: '{column}'. "
    NORMALIZATION_INVALID_CONFIG = "Invalid normalization configuration. Column name '{column}' does not exist. "
    REFERENCE_NORMALIZATION_INVALID_CONFIG = "Invalid normalization configuration. '{nested_ref_name}' not found in the provided data column. "
    RESOURCE_IDENTIFIER_NORMALIZATION_ERR_MSG = "Resource {resource} identifier normalization error when processing data column: '{identifier_column}'. Error: {error_message}"
    MISSING_RESOURCE_IDENTIFIER_COLUMN_ERR_MSG = "Missing resource identifier column: '{identifier_column}' in the dataframe."
    MISSING_RESOURCE_ID_COLUMN_ERROR_MSG = "Missing resource id column: '{resource_id_column}' in the dataframe."
    MISSING_SOURCE_SYSTEM_COLUMN_ERROR_MSG = "Missing source system column: '{source_system_column}' in the dataframe."
    INVALID_RESOURCE_IDENTIFIER_SCHEMA_ERR_MSG = "The schema of the column '{identifier_column}' does not match the expected schema. . Expected schema: {expected_schema}, but got schema: {actual_schema}."
    INVALID_REFERENCE_NORMALIZATION_SOURCE_SYSTEM_ERR_MSG = "Reference normalization failed due to invalid source system. The source_system is `{source_system}`"
    
    # Utils logging messages
    SAVE_DELTA_TABLE_TO_PATH_INFO_MSG = "Saving dataframe to delta table at path: {table_path}"
    UPSERT_UNIQUE_TO_DELTA_MANAGED_SKIPPED = "Skipping upserting the dataframe into {delta_table_path}. The dataframe is empty and the target table already exists"
    UPSERT_UNIQUE_TO_DELTA_MANAGED_PRE_FILTER_INFO_MSG = "Number of records before filtering and upserting into {delta_table_path}: {record_count}"
    UPSERT_UNIQUE_TO_DELTA_MANAGED_POST_FILTER_INFO_MSG = "Number of records pre-filtered out to get the latest unique rows before upserting into {delta_table_path}: {record_count}"
    UPSERT_UNIQUE_TO_DELTA_MANAGED_ERR_MSG = "The provided object is not a DataFrame."
    UPSERT_UNIQUE_TO_DELTA_MANAGED_MERGED_INFO_MSG = "Delta table at path {delta_table_path}: {num_records_persisted} records were successfully persisted and {num_records_filtered} records were filtered based on the {source_timestamp_column} and the insert condition {insert_condition}.Execution time: {execution_time_ms} ms."
    CASTING_FAILED_EXCEPTION_MSG = "Unable to cast value: {value} to type: {type}. Exception: {exception}."
    CASTING_UNSUPPORTED_MSG = "Casting value: {value} to type: {type} is not supported."
    BOOLEAN_CONVERSION_FAILED_MSG = "Failed to convert value: {value} to boolean."

    UPDATE_UNIQUE_TO_DELTA_MANAGED_SKIPPED = "Skipping updating the dataframe into {delta_table_path}. The dataframe is empty and the target table already exists"
    UPDATE_UNIQUE_TO_DELTA_MANAGED_PRE_FILTER_INFO_MSG = "Number of records before filtering and updating into {delta_table_path}: {record_count}"
    UPDATE_UNIQUE_TO_DELTA_MANAGED_POST_FILTER_INFO_MSG = "Number of records pre-filtered out to get the latest unique rows before updating into {delta_table_path}: {record_count}"
    UPDATE_UNIQUE_TO_DELTA_MANAGED_MERGED_INFO_MSG = "Delta table at path {delta_table_path}: {num_records_persisted} records were successfully persisted and {num_records_filtered} records were filtered based on the {source_timestamp_column}.Execution time: {execution_time_ms} ms."
    
    # Folder utils logging message
    FABRIC_MISMATCHED_IDENTIFIERS_ERR_MSG = "Mismatched artifact identifiers:  workspace_name ({workspace_name}) and lakehouse_name ({lakehouse_name}) should both be either Artifact `GUIDs` or `names`."
    WORKLOAD_MISMATCHED_IDENTIFIERS_ERR_MSG = "Mismatched artifact identifiers:  workspace_name ({workspace_name}) and solution_name ({solution_name}) should both be either Artifact `GUIDs` or `names`."

    # FHIRExportService logging messages
    FHIREXPORTSERVICE_RUN_PIPELINE_STARTED_INFO_MSG = "Fhir export service run pipeline started"
    FHIREXPORTSERVICE_RESPONSE_INFO_MSG = "The {trigger_type} HTTP call returned response code {code}"
    FHIREXPORTSERVICE_TRIGGER_SUCCESS_INFO_MSG = "Azure Function triggered. Polling status..."
    FHIREXPORTSERVICE_TRIGGER_ERR_MSG = "Failed to trigger Azure Function. Response code {code}"
    FHIREXPORTSERVICE_EXCEPTION_ERR_MSG = "An exception occured while polling. {exception_message}"
    FHIREXPORTSERVICE_SUCCESS_INFO_MSG = "FHIRExportService completed successfully."
    FHIREXPORTSERVICE_FAILURE_ERR_MSG = "FHIRExportService did not complete as expected."
    FHIREXPORTSERVICE_IN_PROGRESS_DEBUG_MSG = "Azure Function still running..."
    FHIREXPORTSERVICE_POLLING_ERR_MSG = "Polling failed or encountered an error. Response code: {code}. Error message: {message}"
    FHIREXPORTSERVICE_MAX_DURATION_ERR_MSG = "Max polling duration ({max_days} days) reached. Exiting polling loop."
    FHIREXPORTSERVICE_PIPELINE_STATUS_MSG = "Pipeline Success: {result}"
    FHIREXPORTSERVICE_UNABLE_TO_PARSE_ERR_MSG = "Unable to parse error message from output"
    FHIREXPORTSERVICE_NO_ERROR_MSG = "No error message available"

    # Logger name constants
    LogAnalyticsSparkLoggerName = "{logger_name}_LogAnalytics"
    AppInsightsSparkLoggerName = "{logger_name}_AppInsights"
    ConsoleLoggerName = "{logger_name}_Console"
    KustoSparkLoggerName = "{logger_name}_Kusto"
    RunId = "RunId"

    # Claims cms cclf data processing logging messages
    CMS_CCLF_INGESTION_INFO_MSG ="Ingestion {state} CMS CCLF files."
    CMS_CCLF_PROCESS_START_INFO_MSG = "{process_name} {state} for CMS CCLF file."
    CMS_CCLF_CONFIG_NOT_FOUND_ERROR_MSG = "Unable to get input parameters to start processing because of the following error: {message}."
    CMS_CCLF_READING_PROCESS_INFO_MSG ="{state} from {drop_folder}."
    CMS_CCLF_SPARK_STREAM_READ_ERR_MSG = "Failed to read CMS CCLF ingest data for CMS CCLF file located at : {drop_folder} due to following error : {error_msg}."
    CMS_CCLF_SPARK_STREAM_GENERATE_ERR_MSG = "Failed to generate NDJSON for claims due to following error : {error_msg}"
    CMS_CCLF_SUPPORTED_FILE_EXTENSIONS_READ_ERR_MSG = "Failed to read CMS CCLF file extension config."
    CMS_CCLF_DELTA_TABLE_WRITE_STREAM_ERR_MSG = "Unable to write to cclf delta table due to following error: {error_msg}"
    CMS_CCLF_FILE_STARTED_FOR_MSG = "started for "
    CMS_CCLF_FILE_PROCESSING_COMPLETED_MSG = "completed for"    
    CMS_CCLF_STARTED_READING_FILE_CONFIG_MSG = "Started reading cms cclf files configuration."    
    CMS_CCLF_COMPLETED_READING_FILE_CONFIG_MSG = "Completed reading cms cclf files configuration."
    CMS_CCLF_INVALID_FILE_EXTENSION_MSG = "Config error: No valid file extension found for CMS CCLF file."
    CMS_CCLF_LINE_ITEM_LENGTH_MATCHING_MSG = "Length of all the line items in the file {file_extension} are matching expected length."
    CMS_CCLF_CLAIMS_NO_RECORDS_MSG = "No records found in the cms cclf data frame for processing."  
    CMS_CCLF_INVALID_FILE_MOVES_TO_FAILED_FOLDER_MSG =  "The file type for uploaded file: {file} is not supported. Please upload a file with one of the following valid extensions(.T1000001 - .T1000009)."    
    CMS_CCLF_FILE_WITH_MAX_SIZE_MOVES_TO_FAILED_FOLDER_MSG =  "The uploaded file size for file: {file} exceeds the maximum allowed limit. Please upload a file smaller than [{max_file_size}]."    
    CMS_CCLF_FILE_WITH_ATLEAST_ONE_RECORD_NOT_MATCHING_EXPECTED_LENGTH_MSG =  "The file:{file} has been moved to the 'Failed' folder because at least one record did not match the expected length. Please review the file, correct the errors, and try uploading again."
    FILE_COMPRESSION_STATE_INFO_MSG = "{process_name} process {state} at {timestamp} for the source_path files located at {files_path}"
    TOTAL_FILE_COMPRESSION_INFO_MSG = '{process_name} - Total number of files compressed : {compressed_files_count}'
    TOTAL_FILE_DELETION_INFO_MSG = '{process_name} - Total number of source files deleted : {deleted_files_count}'
    CMS_CCLF_OBJECTS_PER_SOURCE_INFO_MSG = "Saving {num_records} ExplanationOfBenefit fhir records for source system : '{source_system}'."
    CMS_CCLF_SPARK_STREAM_GENERATE_INFO_MSG = "Sparkstream initiated "	

    TABLE_NOT_FOUND_ERR_MSG = "Unable to find table {table_name} in lakehouse."
    CCLF_VIEW_CREATION_FAILED_ERR_MSG = "Failed to create view {view_name} in lakehouse."
    READ_STREAM_PROCESS_INFO_MSG = "{state} from {drop_folder}."
    SPARK_READ_STARTED = "Spark read streaming started "    
    SPARK_READ_COMPLETED = "Spark read streaming completed "
    # Dicom imaging logging messages
    PROCESSING_STATE_INFO_MSG = "{process_name} process {state} at {timestamp} for DCM imaging files located at {dcm_files_path}."
    FAILED_FILES_NOT_MOVED_ERR_MSG = "Unable to move failed files due to following error: {error_msg}"
    FAILED_FILES_INFO_COLLECT_ERR_MSG = "Unable to collect failed files information due to the following error: {error_msg}"
    PATH_NOT_REMOVED_ERR_MSG = "The path '{path}' could not be removed. {exception}"
    RETRY_INFO_MSG = "{process_name} process attempt: {retry_attempt}"
    TAGS_EXTRACTION_FAILED_MSG = "Dicom metadata tags extraction in dcm file: {dcm_file_name} failed for the following tags : {failed_tags}"
    PROCESSING_FAILED_ERR_MSG = "{process_name} process failed for dcm file : {dcm_file_name} due to following error : {error_mssg}"
    PROCESSING_STATUS_INFO_MSG = "\nTotal DCM files : {total_dcm_files} \nSuccessful files : {success_files_count} \nFailed files : {failed_files_count} \n\tRetriable Failed files : {retriable_failed_files_count} \n\tNon-Retriable Failed files : {non_retriable_failed_files_count}"
    MULTIPLE_INVENTORY_PROCESSING_ERR_MSG = "Multiple inventory processing at the same time is not supported. Configure the job to only pick one set of inventory files at a time. Found inventory files at : \n{inven_files_path[0]}\n{inven_files_path[1]}"
    INVENTORY_FILES_NOT_ORGANIZED_ERR_MSG = "Processing of all Inventory Files has failed and stopped. There are (#) Inventory Files (see top 10 below) that are not organized in date (yyyy/mm/dd) hierarchy parent folders {inventory_path}"
    INVENTORY_NS_MAXDATE_INFO_MSG = "Current namespace : {namespace} - max processed date: {max_processed_date} from ImagingDicom table inventory files"
    
    # Dicom Metadata to fhir ImagingStudy conversion logging messages
    NO_NEW_DATA_FOUND_INFO_MSG = "No new data found in ImagingDicom table for processing."
    SAVING_NDJSON_FILE_INFO_MSG = "Saving fhir ndjson file with {num_records} records at {file_path}."
    FHIR_CONVERSION_PROCESS_STATE_INFO_MSG = "DICOM Metadata to FHIR conversion process (Epoch id: {epoch_id}) {state} at {timestamp} for ImagingDicom table located at : {table_loc}"
    RECORDS_NUM_PROCESSED_INFO_MSG = "From the previous run, total number of {records_num} new records found in ImagingDicom table for conversion."
    FHIR_ELEMENT_GROUPING_INFO_MSSG = "Aggregating information at '{fhir_element_name}' fhir object level."
    SPARK_STREAM_READ_ERR_MSG = "Failed to read ImagingDicom table located at : {table_path} due to following error : {error_msg}"
    IMAGING_STUDY_OBJECTS_PROCESSED_INFO_MSG = "Total number of ImagingStudy fhir records processed in this run : {num_records}"
    IMAGING_STUDY_OBJECTS_PER_SOURCE_INFO_MSG = "Saving {num_records} ImagingStudy fhir records for source system : '{source_system}'."

    # ImagingMetaStoreCreator logging messages
    SPARK_CUSTOM_STREAM_READ_ERR_MSG = "Failed to read source table located at : {table_path} due to following error : {error_msg}"
    SAVING_RESOURCE_ERR_MSG = "Error occurred while saving data into target table: {table_path} due to following error : {error_msg}"
    EMPTY_DATAFRAME = "Empty dataframe is passed"
    BEGAN_CUSTOM_TABLE_EXECUTION_INFO_MSG = "Began execution for table {source_table} transformation to {target_table} at {timestamp} from source to target lakehouse."
    COMPLETED_CUSTOM_TABLE_EXECUTION_INFO_MSG = "Completed execution for table {source_table} transformation to {target_table} at {timestamp} from source to target lakehouse."
    CONFIG_MAPPING_ERROR_MSG = "Error occurred while reading expression for field 'id' in config mappings at config path: {config_file_path}."
    
    IMAGING_INVALID_PROCESS_TYPE_ERR_MSG = "Invalid process type: {process_type}. Expected 'dicom' or 'patch'."    
    IMAGING_METASTORE_PROCESSING_STATE_INFO_MSG = "{process_name} process {state} at {timestamp} for {process_type}"
    IMAGING_METASTORE_ID_GENERATION_COMPLETED_INFO_MSG = "Id generation completed"
    IMAGING_METASTORE_PRE_PROCESSING_STATE_INFO_MSG = "Pre-process for {operation} operation is {state} at {timestamp}"
    IMAGING_METASTORE_SAVE_STATE_INFO_MSG = "Saving process {state} with process_type {process_type} and operation {operation} for ImagingMetastore."
    
    # Imaging PATCH File Ingestion logging messages
    IMAGING_PATCH_FILE_PROCESSING_STATE_INFO_MSG = "{process_name} process {state} at {timestamp} for PATCH files located at {file_path}."
    IMAGING_PATCH_FILE_PROCESSING_SUMMARY_INFO_MSG = "\nTotal PATCH files : {total_patch_files} \nSuccessful files : {success_files_count} \nFailed files : {failed_files_count} \ntimestamp : {timestamp} \nnamespace : {namespace}"
    IMAGING_PATCH_PROCESSING_FAILED_ERR_MSG = "{process_name} process failed for PATCH file : {file_name} due to following error : {error_mssg}"
    IMAGING_PATCH_VALIDATION_FAILED_AGGREGATED_ERR_MSG = "{process_name} process failed for PATCH files due to following error : {error_mssg}"
    IMAGING_PATCH_FILE_VALIDATION_FAILED_ERR_MSG = "The Patch File Ingestor service failed with validation."
    IMAGING_PATCH_FILE_FAILED_BS = "Patch file processing failed"
    IMAGING_PATCH_FILE_MOVE_FAILED_FILE_BS = "Failed while moving failed PATCH files"
    IMAGING_PATCH_FILE_UNHANDLED_ERROR = "Un handled exception during PATCH file processing"
    
    NO_NEW_DATA_FOUND_WITH_OPERATION_INFO_MSG = "No new data found with {operation} - operation for processing."
     
    # Patient Outreach
    POA_INGESTION_START_INFO_MSG = 'Patient outreach ingestion started.'
    POA_INGESTION_COMPLETED_INFO_MSG = 'Patient outreach ingestion completed.'
    POA_CREATE_CDS_SHORTCUT_TABLES_START_INFO_MSG = 'Patient outreach create CDS shortcut tables started.'
    POA_CREATE_CDS_SHORTCUT_TABLES_COMPLETED_INFO_MSG = 'Patient outreach create CDS shortcut tables completed.'
    POA_CREATE_MARKETING_ANALYSIS_SHORTCUT_TABLES_START_INFO_MSG = 'Patient outreach create marketing analysis shortcut tables started.'
    POA_CREATE_MARKETING_ANALYSIS_SHORTCUT_TABLES_COMPLETED_INFO_MSG = 'Patient outreach create marketing analysis shortcut tables completed.'
    POAGOLD_TRANSFORMATION_EXCEPTION_ERROR_MSG = "Patient Outreach GOLD transformation failed. {0} raised. Details: {1}."

    # DTT Workflow logging messages
    DTT_CONFIG_FILES_EMPTY_MSG = "Config files must be provided to run RMT and DMT transformation."
    DTT_SERVICE__SUCCESS_INFO_MSG = "DTT workflow completed successfully. The output is available at {0} and {1}."

    # Claims Data Ingestion logging messages
    CCLF_NO_NEW_DATA_FOUND_INFO_MSG = "No new data found in claims delta tables for processing."
    CCLF_RECORDS_NUM_PROCESSED_INFO_MSG = "From the previous run, total number of {records_num} new records found in CCLF Delta tables for conversion."
    CCLF_FHIR_CONVERSION_PROCESS_STATE_INFO_MSG = "CCLF to FHIR conversion process (Epoch id: {epoch_id}) {state} at {timestamp} for claims delta tables located at : {table_loc}"
    CCLF_CLAIMS_VIEW_CREATED_INFO_MSG = "{view_name} successfully created."
    CCLF_SQL_QUERY_EXECUTION_STARTED_INFO_MSG = "SQL Query execution for {view_name} started at {timestamp}"
    CCLF_SQL_QUERY_EXECUTION_COMPLETED_INFO_MSG = "SQL Query execution for {view_name} completed at {timestamp}"

    #Business Events Logging Messages
    BE_FAILED_FILE_MESSAGE = "Failed to process file at filePath: {file_path} "
    BE_FAILED_CORRUPT_FILE_MESSAGE = "Failed to process file at filePath: {file_path} "
         
    # CMA
    CMA_INGESTION_START_INFO_MSG = 'CMA ingestion started.'
    CMA_INGESTION_COMPLETED_INFO_MSG = 'CMA ingestion completed.'
    CMA_TRANSFORMATION_EXCEPTION_ERROR_MSG = "CMA transformation failed. {0} raised. Details: {1}."

    # File Orchestration Logging Messages
    FILE_ORCHESTRATION_SERVICE_START_INFO_MSG = 'File orchestration service started.'
    READING_FILE_ORCHESTRATION_CONFIG_INFO_MSG = "Reading the file orchestration configuration file at {file_orchestration_config_path}"
    FILE_ORCHESTRATION_PROCESSING_STATUS_INFO_MSG = "\n\n\tModality Information : `{modality_name}`\n\tTotal number of files : {total_files_count} \n\tSuccessful files : {success_files_count} \n\tFailed files : {failed_files_count}\n\tOrchestration Type : {orchestration_type}\n\n"
    FO_EXTRACT_PROCESS_STATE_INFO_MSG = "Archive extraction process {state} for Modality `{modality_name}`, extracting files to {target_path_to_extract}"
    FO_MOVEMENT_PROCESS_STATE_INFO_MSG = "File movement process `{state}` for Modality `{modality_name}`, moving files to {target_path_to_move}"
    FO_NO_FILES_FOUND_INFO_MSG = "No files found to `{orchestration_type}` for Modality `{modality_name}`. Please ensure files are located in {source_path}"
    FO_PROCESSING_FAILED_ERR_MSG = "Error occurred while processing files for Modality `{modality_name}` due to following error : {error_mssg}"
    FO_VERIFY_SOURCE_PATH_INFO_MSG = "\n\nVerifying if source_path exists for the `{modality_name}` modality"
    FO_MODALITY_PATH_FOUND_INFO_MSG = "Modality : `{modality_name}` folder found at {source_file_path}, continuing the next step of processing"
    FO_NO_NAMESPACE_FOUND_INFO_MSG = "Source path {source_file_path} does not contain any `namespace` folders for `{modality_name}`"
    FO_SOURCE_PATH_NOT_FOUND_INFO_MSG = "Source path {source_file_path} does not exists for `{modality_name}`"
    FO_DELETING_EMPTY_SOURCE_DIRECTORIES = "Finished moving files in namespace: {namespace}, Deleting empty source directories."

    # Parameter Collection Logging Messages
    PARAMETER_USING_INLINE_PARAM_VALUE = "For key '{key_name}', using inline parameter value '{value}'"
    PARAMETER_USING_FOUNDATION_CONFIG_VALUE = "For key '{key_name}', using the global config value '{value}'. Config path: {config_path}"
    PARAMETER_USING_ACTIVITY_CONFIG_VALUE = "For key '{key_name}', using activity config value '{value}'. Config path: {config_path}"
    PARAMETER_ERROR_FOUNDATION_CONFIG_VALUE = "Unable to retrieve the key '{key_name}' from the global config. Config path: {config_path}. Using Default value."
    PARAMETER_ERROR_ACTIVITY_CONFIG_VALUE = "Unable to retrieve the key '{key_name}' from the activity config. Config path: {config_path}. Using Default value."
    REQUIRED_PARAMS_MISSING_ERR_MSG = "Required parameters are missing. Please ensure the following parameters are present: '{missing_params}'"

    #DTT Generic Service logging messages
    GENERIC_DTT_TRANSFORMATION_INLINE_PARAM_ERROR_MSG = "DTT transformation service require, {0} input parameter. Please provide: {0}."
    # IDM
    IDM_INGESTION_START_INFO_MSG = 'IDM ingestion started.'
    IDM_INGESTION_COMPLETED_INFO_MSG = 'IDM ingestion completed.'

    # Vocab Service
    VOCAB_INGESTION_START_INFO_MSG = 'Vocab ingestion started.'
    VOCAB_INGESTION_COMPLETED_INFO_MSG = 'Vocab ingestion completed.'
    
    # Execution Metrics Logging Messages
    METRICS_INVALID_METRICS_KEY_ERR_MSG = "Invalid key: {key}. All keys in the execution metrics must be strings"
    METRICS_INVALID_METRICS_VALUE_ERR_MSG = "Invalid value for key '{key}': {value}. All values in execution metrics must be integers or floats"
    METRICS_INVALID_METRICS_DATATYPE_ERR_MSG = "Invalid datatype for execution metrics : {metrics}. Execution metrics must be a dictionary"
    METRICS_INVALID_GRANULAR_METRICS_DATATYPE_ERR_MSG = "Invalid value for key '{key}': {value}. All values in granular execution metrics must be dictionaries"
    METRICS_INVALID_GRANULAR_METRICS_KEY_ERR_MSG = "Invalid table name: {table_name}. All keys in the dictionary must be strings"
    METRICS_INVALID_GRANULAR_METRICS_VALUE_ERR_MSG = "Invalid count for table '{table_name}': {count}. All values in the dictionary must be integers"
    METRICS_INVALID_ACCUMULATOR_ERR_MSG = "Accumulator for stage '{accumulator_activity_id}' is not registered."
    METRICS_DUPLICATE_ACCUMULATOR_ERR_MSG = "Accumulator for stage '{accumulator_activity_id}' is already registered."
    METRICS_ORCHESTRATOR_INFO_MSG = "Persisted HDS summary metrics for pipeline activity '{activity_display_name}' to Delta table at '{execution_summary_table_path}'. Use the following query to retrieve the pipeline summary: SELECT * from ExecutionSummary WHERE runId = {run_id}"
    METRICS_ORCHESTRATOR_SUMMARY_INFO_MSG = "The {activity_display_name} summary metrics: {summary_metrics}"    
    CREATING_EXECUTION_SUMMARY_TABLE_INFO_MSG = "Execution Summary Table does not exist. Creating execution summary table at {delta_table_path}"
    POLLING_METRICS_INFO_MSG = "Polling execution metrics every {polling_interval_seconds} seconds for activity: {activity_display_name}."
    POLLING_METRICS_STARTED_INFO_MSG = "Started metrics poller for activity: {activity_display_name} with a polling interval of {metrics_polling_interval_min} minutes."
    POLLING_METRICS_STOPPED_INFO_MSG = "Stopped metrics poller."
    POLLING_METRICS_FAILED_ERR_MSG = "Failed to poll metrics for activity: {activity_display_name}. Error details: {error_message}"
    COLLECT_METRICS_FAILED_ERR_MSG = "Failed to collect the target delta table operation summary metrics for activity: {activity_name}. Error details: {error_message}"    
    COLLECT_ALL_TABLES_METRICS_ERR_MSG = "Failed to collect metrics for {activity_name} from the tables in {target_tables_root_path}: {error_message}"    
    # Library Usage Telemetry
    LIBRARY_USAGE_TELEMETRY_INFO_MSG = "The {internal_activity_name} library usage metrics reported: {library_usage_attributes}"
    
    # Base Runnable Service Logging Messages
    SERVICE_EXECUTION_STARTED_INFO_MSG = "The activity '{activity_name}' execution has started."
    SUCCESSFUL_EXECUTION_INFO_MSG = "The activity '{activity_name}' execution has completed successfully."
    PENDING_EXECUTION_INFO_MSG = "The activity '{activity_name}' execution is pending completion."
    FAILED_EXECUTION_ERR_MSG = "The activity '{activity_name}' execution has failed. Error details: {error_message}"
    SUCCESSFULLY_COMPLETED_WITH_VALIDATION_WARNINGS_MSG = "The activity '{activity_name}' execution completed successfully with validation warnings. The individual warnings can be found in the BusinessEvents table in the Admin lakehouse. Use the following query to identify the validation warnings that were encountered: SELECT * from BusinessEvents where runId = {run_id}"
    SUCCESSFUL_EXECUTION_WITH_ERRORS_INFO_MSG = "The activity '{activity_name}' execution completed with errors. The individual errors can be found in the BusinessEvents table in the Admin lakehouse. Use the following query to identify the errors that were encountered: SELECT * from BusinessEvents where runId = {run_id}. Error details: {error_message}"    
    UNSUPPORTED_SOURCE_TYPE = "Unsupported source type '{source_type}'."
    TRANSFORMATION_COMPLETED_SUCCESSFULLY = "Transformation completed successfully for source type '{source_type}'."
    TRANSFORMATION_FAILED = "Transformation failed for source type '{source_type}' due to error - {error_message}."
    INGESTION_ERROR_MSG = "Error during {source_type} ingestion: {error_msg}"
    SETUP_ERROR_MSG = "Error during service setup: {error_msg}"



