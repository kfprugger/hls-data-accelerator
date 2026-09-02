# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------

class AIEnrichmentsLoggingConstants:
    
    #Bronze Ingestion
    AI_ENRICHMENT_BRONZE_INGESTION_START_INFO_MSG = 'AI Enrichment Bronze ingestion started.'
    AI_ENRICHMENT_BRONZE_INGESTION_COMPLETED_INFO_MSG = 'AI Enrichment Bronze ingestion completed.'
    AI_ENRICHMENT_BRONZE_INGESTION_EXECUTION_ERROR = 'Error while executing AI Enrichment Bronze Ingestion. {error}'
    AI_ENRICHMENT_BRONZE_FAILED_TO_FILTER_VALID_INVALID_ROWS_ERROR_MSG = 'Failed to filter valid and invalid rows. Error: {error}'
    AI_ENRICHMENT_BRONZE_FAILED_TO_MOVE_FILES_TO_FAILED_FOLDER= 'Failed to move file {file} to failed folder. Error: {error}'
    AI_ENRICHMENT_BRONZE_FAILED_TO_HANDLE_INVALID_ROWS_ERROR_MSG = 'Failed to handle invalid file movement. Error: {error}'
    AI_ENRICHMENT_BRONZE_FILE_MOVEMENT_FAILED_MSG = "File failed to pass validation and was moved to the failed folder. Make sure the file has a valid JSON and conforms to the schema."
    #Silver Ingestion
    AI_ENRICHMENT_SILVER_INGESTION_START_INFO_MSG = "AI Enrichment Silver ingestion started."
    AI_ENRICHMENT_SILVER_INGESTION_COMPLETED_INFO_MSG = "AI Enrichment Silver ingestion Completed."
    AI_ENRICHMENT_SILVER_INGESTION_EXECUTION_ERROR = 'Error while executing AI Enrichment Silver Ingestion. {error}'
    AI_ENRICHMENT_SILVER_FAILED_TO_STREAM_RESOURCE_ERROR_MSG = "Failed to process  resource {resource_name}. Error: {exception_details}"

    #Execution Service
    AI_ENRICHMENT_EXECUTE_STARTED_INFO = "Enrichment execution initiated for {inputs_count} records with generation ID: {generation_id}."
    AI_ENRICHMENT_ENRICHMENT_EXECUTION_ERROR="AI Enrichment Service execution failed"
    AI_ENRICHMENT_ENRICHMENT_SERVICE_START="Enrichment execution started"
    AI_ENRICHMENT_ENRICHMENT_SERVICE_SUCCESS="Enrichment completed successfully"
    AI_ENRICHMENT_MODEL_EXECUTION_IMPLEMENTATION_ERROR = 'Subclasses must implement this method.'
    AI_ENRICHMENT_INVALID_ENRICHMENT_EXECUTION_PARTITION = "Invalid number of partitions specified for enrichment execution. It must be >= 1."
    AI_ENRICHMENT_INVALID_ENRICHMENT_SAVE_PARTITION = "Invalid number of partitions specified for enrichment save. It must be >= 1."
    AI_ENRICHMENT_ENRICHMENT_EXECUTION_REPARTITION = "Repartitioned DataFrame to {n_partitions} partitions"
    AI_ENRICHMENT_ENRICHMENT_SERVICE_INIT_ERROR="AI Enrichment Service initialization failed"
    AI_ENRICHMENT_TRANSFORMER_PROCESS_STARTED_INFO = "Transformation of model outputs has started"
    AI_ENRICHMENT_PROCESS_TRANSFORMATION_COMPLETED_INFO = "Enrichment transformation finished for {processed_count} records from a total of {inputs_count}"
    AI_ENRICHMENT_SAVE_RESULTS_TO_PATH_INFO = "Saving enrichment results to path: {path}."
    AI_ENRICHMENT_ENRICHMENT_METADATA_SERVICE_INIT_START="AI Enrichment Metadata Service initialization started"
    AI_ENRICHMENT_ENRICHMENT_EXECUTION_SERVICE_INIT_START="AI Enrichment Execution Service initialization started"
    AI_ENRICHMENT_MODEL_PROCESS_EMPTY_RESPONSE_ERROR="Enrichment Model processor returned no data for transformation"
    AI_ENRICHMENT_MODEL_VIEW_QUERY_EMPTY_INFO="No records found for enrichment with ID: {enrichment_id}"
    AI_ENRICHMENT_NO_ACTIVE_ENRICHMENT_CONTEXTS="No active enrichment contexts found for the given generation ID: {generation_id}"
    AI_ENRICHMENT_MODEL_PROCESS_EXECUTION_INFO="Model processor execution for enrichment has started with {records_count} records."
    AI_ENRICHMENT_ENRICHMENT_MODEL_EXECUTION_ERROR="Error while executing model processor"
    AI_ENRICHMENT_MODEL_PROCESS_COMPLETED_BATCH_INFO="Model execution completed for batch of documents {start_index} to {end_index}"
    AI_ENRICHMENT_TRANSFORMATION_RECORDS_INFO="Enrichment data transformation started with {records_count} responses."
    AI_ENRICHMENT_CONTEXT_NOT_FOUND_WARNING="Enrichment context not found for Id: {id}"
    AI_ENRICHMENT_LOGGER_NAME_EMPTY_ERROR = "Logger name must be provided to initialize the logger."
    AI_ENRICHMENT_TA4H_CLIENT_EXECUTION_ERROR="Error during Text Analytics client execution: {error}"

    
    #AIEnrichment Metadata Service and metadata repository
    ENRICHMENT_VIEW_DELETED = "Enrichment view '{0}' removed from table '{1}'."
    MATERIALIZED_VIEW_DELETED = "Materialized view '{0}' removed."
    ENRICHMENT_VIEW_NOT_FOUND = "No enrichment view found with ID '{0}'."
    ENRICHMENT_NOT_FOUND = "No enrichment found with ID '{0}'."
    MATERIALIZED_VIEW_NOT_FOUND = "No materialized view found with ID '{0}'."
    ENRICHMENT_METADATA_CREATED = "Enrichment metadata created in table '{0}' with ID '{1}'."
    ENRICHMENT_CONTEXT_CREATED = "Enrichment context created with ID '{0}'."
    ENRICHMENT_DATA_SAVED = "Enrichment metadata saved to table '{0}'."
    ERROR_DELETING_RECORD = "Failed to delete record with ID '{0}' from table '{1}': {2}."
    RECORD_INFO_RETRIEVED = "Data retrieved from table '{0}' with ID '{1}'."
    ERROR_RETRIEVING_RECORD_INFO = "Failed to retrieve record info for table '{0}' with ID '{1}': {2}."
    ENRICHMENT_CONTEXT_NOT_FOUND = "No enrichment context found with ID '{0}'."
    ERROR_UPSERTING_CONTEXT_DATA = "Failed to upsert enrichment context data: '{0}'"
    ERROR_INITIALIZING_METADATA_STORE="Failed to initialize metadata store: {0}"
    
    #OPENAI Client
    OPENAI_DATA_ENRICHMENT_TOKENS_USAGE_INFO_MSG = "Total token usage for this enrichment: {token_count}"
    OPENAI_DATA_ENRICHMENT_AI_COMPLETION_ERROR = "An error occurred while generating the completion"
    OPENAI_DATA_OUTPUT_NONE_WARNING = "Failed to generate enrichment data"
    OPENAI_ENRICHMENT_MODEL_CONFIG_ERROR="The model configuration parameters are missing"
    OPENAI_ENRICHMENT_INVALID_API_KEY="The provided API key for the model configuration is invalid"
    
    #MedImageInsight Client
    MED_IMAGE_INSIGHT_OUTPUT_RESPONSE_WARNING = "Unexpected output response: '{response}'"
    MED_IMAGE_INSIGHT_FILE_PROCESSING_ERROR="Error processing file: {filename}. Error message: {error_message}"
    
    #MedImage parse
    MED_IMAGE_PARSE_FILE_PROCESSING_ERROR="Unable to transform medimage parse response"

    #Client Orchestrator
    AI_ENRICHMENT_CLIENT_ORCHESTRATOR_INIT_INFO = "Initializing AI Enrichment Client Orchestrator:{Type}"
    AI_ENRICHMENT_CLIENT_EXECUTION_ERROR="Error executing AI Enrichment Client Orchestrator :{error}"
    AI_ENRICHMENT_CLIENT_INVALID_INPUT = 'Client execution failed due to missing required input parameters'
    
    
    