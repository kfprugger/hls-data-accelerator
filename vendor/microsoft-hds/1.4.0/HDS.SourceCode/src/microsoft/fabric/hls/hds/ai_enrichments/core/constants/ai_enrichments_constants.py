# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
from pyspark.sql.types import StructType, StructField, StringType, TimestampType, ArrayType, MapType

class AIEnrichmentsConstants:
    """
    This class contains constants and schema definitions used for AI Enrichment processes.
    """
    DEFAULT_AI_ENRICHMENT_EXECUTION_BATCH_SIZE = 25
    AI_ENRICHMENTS_MODALITY_NAME = "AIEnrichments"
    
    ENRICHMENT_LANDING_ZONE_PATH = "Ingest/AIEnrichments"
    ENRICHMENT_LANDING_ZONE_DIR = "Fabric-HDS"
    ENRICHMENT_LANDING_ZONE_RAW_RESPONSE_PATH = "raw_response"
    DEFAULT_AI_ENRICHMENT_EXECUTION_THREADS = 10
    DEFAULT_AI_ENRICHMENT_MII_EXECUTION_THREADS = 2
    DEFAULT_AI_ENRICHMENT_EXECUTION_THREADS_LIMIT_KEY = "enrichment_execution_threads_limit"
    DEFAULT_AI_ENRICHMENT_LANDING_ZONE_PATH_KEY = "ai_enrichment_landing_zone_path"
    AI_ENRICHMENT_EXECUTION_ACTIVITY_NAME = "ai-enrichment-execution"
    AI_ENRICHMENT_METADATA_ACTIVITY_NAME = "ai-enrichment-metadata"
    AI_ENRICHMENT_ORCHESTRATOR_ACTIVITY_NAME="ai-enrichment-orchestrator"
    REFRESH_METADATA_KEY = "refresh-metadata"
    ENRICHMENT_API_SECRET_KEY_NAME="api_key_secret_name"
    ENRICHMENT_API_KV_KEY_NAME="kv_uri"
    ENRICHMENT_EXECUTION_PARTITION= "ExecutionPartition"
    ENRICHMENT_EXECUTION_PARTITION_VALUE = 1
    ENRICHMENT_SAVE_PARTITION= "SavePartition"
    ENRICHMENT_SAVE_PARTITION_VALUE = 5
    ENRICHMENT_EXECUTION_MODE = "ExecutionMode"
    ENRICHMENT_EXECUTION_MODE_VALUES = ["distributed", "driver"]
    ENRICHMENT_PARTITION_CONFIG_DEFAULT: dict = {
        ENRICHMENT_EXECUTION_PARTITION: ENRICHMENT_EXECUTION_PARTITION_VALUE,
        ENRICHMENT_SAVE_PARTITION: ENRICHMENT_SAVE_PARTITION_VALUE,
        ENRICHMENT_EXECUTION_MODE: ENRICHMENT_EXECUTION_MODE_VALUES[0],
    }
    
    


    # AIEnrichment Metadata Store
    ENRICHMENT_TABLE = 'Enrichment'
    ENRICHMENT_MATERIALIZED_TABLE = 'EnrichmentMaterializedView'
    ENRICHMENT_CONTEXT_TABLE = 'EnrichmentContext'
    ENRICHMENT_VIEW_TABLE = 'EnrichmentView'
    ENRICHMENT_GENERATED_INFO_TABLE = 'EnrichmentGeneratedInfo'
    ENRICHMENT_METADATA_LAKEHOUSE_ID_KEY = "metadatastore_lakehouse_id"
    ENRICHMENT_METADATA_LAKEHOUSE_ID_NAME = "metadatastore_lakehouse_name"
    ENRICHMENT_RECORDS_LIMIT_KEY = 'enrichment_records_limit'
    ENRICHMENT_RECORDS_LIMIT_DEFAULT_VALUE = 100
    ENRICHMENT_RECORDS_SAVE_RAW_RESPONSE_KEY = "save_model_raw_response"
    ENRICHMENT_MODEL_CONFIG_EXCLUDE_KEYS = "model_config_exclude_keys"
    ENRICHMENT_MODEL_CONFIG_EXCLUDE_VALUES = "api_key,kv_uri,api_key_secret_name"
    ENRICHMENT_RECORDS_OUTPUT_LIMIT_KEY = "enrichment_records_output_limit_per_file"
    ENRICHMENT_RECORDS_OUTPUT_LIMIT_DEFAULT_VALUE = 100
    ENRICHMENT_EXECUTION_COLLECT_BATCH_SIZE_KEY = "enrichment_execution_collect_batch_size"
    ENRICHMENT_EXECUTION_COLLECT_BATCH_SIZE_DEFAULT_VALUE = 1000
    ENRICHMENT_MATERIALIZED_VIEWS_PATH ="MaterializedViews"
    ENRICHMENT_MATERIALIZED_FILE_PREFIX ="MaterializedView"
    ENRICHMENT_INPUT_MAPPING_NOT_FOUND = "Input mapping is not found in the enrichment definition for the ID: {enrichment_id}"
    ENRICHMENT_DEFINITION_NOT_FOUND = "Enrichment definition is not found for the ID: {enrichment_id}"
    ENRICHMENT_VIEW_ID_NOT_FOUND = "The provided view ID: {view_id} is invalid"
    ENRICHMENT_VIEW_INFO_NOT_FOUND = "Enrichment view information is not found for the view ID: {view_id}"
    ENRICHMENT_VIEW_USING_EXISTING_VIEW = "Enrichment view already exists. Using the existing view ID: {view_id}."
    ENRICHMENT_VIEW_NAME_ALREADY_EXISTS = "Enrichment view with the name '{view_name}' already exists. Please choose a different name."
    ENRICHMENT_INVALID_QUERY_TYPE = "An invalid query type is found in the enrichment view definition for the ID: {enrichment_view_info_id}"
    ENRICHMENT_SQL_QUERY_NOT_FOUND = "SQL query is not found in the enrichment view definition for the ID: {enrichment_view_info_id}"
    ENRICHMENT_SQL_QUERY_INVALID = "The SQL query is not valid for the enrichment view ID: {enrichment_view_info_id}"
    ENRICHMENT_PARENT_VIEW_INFO_NOT_FOUND = "Parent view information is not found for the ID: {parent_id}"
    ENRICHMENT_METADATA_PATIENT_ID_NOT_FOUND = "Patient ID is not found in the enrichment metadata"
    ENRICHMENT_RESOURCE_REFERENCES_NOT_FOUND = "Resource references must contain at least one column mapping definition"
    ENRICHMENT_ID_AND_CONTENT_NOT_EMPTY = "The ID and content must not be empty"
    ENRICHMENT_UNEXPECTED_ERROR = "An unexpected error occurred in the {method} method: {error}"
    ENRICHMENT_MODEL_CONFIGURATION_INVALID = "The model configuration is invalid. Both the API endpoint and API key must be provided."
    ENRICHMENT_OUTPUT_SAVE_INFO = "Successfully saved the results of batch number {batch_number} to the specified output path: {final_output_path}."
    ENRICHMENT_CONTEXT_SAVE_ERROR_MSG = "An error occurred while saving the enrichment context data to the specified output path: {error}."
    ENRICHMENT_VIEW_QUERY_RESULT_EMPTY="No data found for enrichment view ID: {enrichment_view_info_id}"
    ENRICHMENT_RESULTS_TMP_PATH ="EnrichmentResults"
   
    # Bronze Ingestion
    ENRICHMENT_LANDING_ZONE_LAKEHOUSE_ID_KEY = "ai_enrichment_landing_zone_lakehouse_id"
    ENRICHMENT_MAX_DATA_COLUMN_SIZE = 30000000
    ENRICHMENT_TARGET_BRONZE_TABLE_NAME_KEY = "ai_enrichment_target_bronze_table_name"
    ENRICHMENT_SOURCE_TABLE_NAME_KEY = "ai_enrichment_source_table_name"
    DEFAULT_ENRICHMENT_TARGET_BRONZE_TABLE_NAME = "AIEnrichments"
    AI_ENRICHMENTS_SUPPORTED_FILE_TYPES= ["json", "ndjson"]
    ENRICHMENT_RESOURCE_SCHEMA_NOT_FOUND_ERROR_MSG = "The resource schema is not found for resource: {resource_name}"
    ENRICHMENT_FAILED_TO_PARSE_COMMON_CONTEXT_ERROR_MSG = "Failed to parse the common context data: {error}"
    AI_ENRICHMENT_BRONZE_INGESTION_VALIDATION_WARNING_MSG = "File: {file_path} has validation errors. Check the BusinessEvent table for details"
    AI_ENRICHMENT_FLAT_FHIR_OBJECT_TABLE_NAME = "FlatFhirObject"

    # Bronze column names
    ENRICHMENT_BRONZE_DATA_COLUMN = "data"
    ENRICHMENT_BRONZE_FILENAME_COLUMN = "file_name"
    ENRICHMENT_BRONZE_VALUE_COLUMN = "value"
    ENRICHMENT_BRONZE_PROCESS_TIME_COLUMN = "process_time"
    ENRICHMENT_BRONZE_FULL_FILE_PATH_COLUMN = "file_path"
    ENRICHMENT_BRONZE_ENRICHMENT_TYPE_COLUMN = "type"
    ENRICHMENT_BRONZE_CONTEXT_COLUMN = "context"
    ENRICHMENT_BRONZE_PARENT_FOLDER_REGEX = r"/([^/]+)/[^/]+/[^/]+/[^/]+/[^/]+/[^/]+$"
    ENRICHMENT_BRONZE_FILENAME_REGEX= r"([^/]+$)"
    ENRICHMENT_BRONZE_PARSED_DATA_COLUMN= "parsed_data"
    ENRICHMENT_BRONZE_PARSED_CONTEXT_COLUMN= f"{ENRICHMENT_BRONZE_PARSED_DATA_COLUMN}.context"
    ENRICHMENT_BRONZE_PARSED_PATIENT_ID_COLUMN= f"{ENRICHMENT_BRONZE_PARSED_DATA_COLUMN}.context.enrichment_input.patient_id"
    ENRICHMENT_BRONZE_PATIENT_ID_COLUMN= "patient_id"
    ENRICHMENT_BRONZE_CREATED_DATETIME_COLUMN = "createdDatetime"
    
    # Common Silver Columns
    ENRICHMENT_UNIQUE_ID_COLUMN = "id"
    ENRICHMENT_CONTEXT_COLUMN = "context"
    ENRICHMENT_CONTEXT_ID_COLUMN = "enrichment_context_id"
    ENRICHMENT_GENERATION_ID_COLUMN = "enrichment_generation_id"
    ENRICHMENT_DEFINITION_ID_COLUMN = "enrichment_definition_id"
    ENRICHMENT_SILVER_DATA_COLUMN = "data"
    ENRICHMENT_SILVER_PARSED_COLUMN = "parsed"
    ENRICHMENT_SILVER_MODEL_NAME_COLUMN = "model_name"
    ENRICHMENT_SILVER_MODEL_VERSION_COLUMN = "model_version"
    ENRICHMENT_SILVER_PATIENT_ID_COLUMN = "patient_id"
    ENRICHMENT_SILVER_METADATA_COLUMN = "metadata"
    ENRICHMENT_SILVER_OUTPUTS_COLUMN = "outputs"
    ENRICHMENT_SILVER_VALUE_COLUMN = "value"
    ENRICHMENT_SILVER_CONFIDENCE_SCORE_COLUMN = "confidence_score"
    ENRICHMENT_SILVER_DESCRIPTION_COLUMN = "description"
    ENRICHMENT_SILVER_UNIQUE_ID_COLUMN = "unique_id"
    
    # Common Silver JSON Paths
    ENRICHMENT_JSON_PATH_CONTEXT = "$.context"
    ENRICHMENT_CONTEXT_MODEL_CONFIGURATION_NAME = f"{ENRICHMENT_SILVER_PARSED_COLUMN}.{ENRICHMENT_CONTEXT_COLUMN}.model_configuration.name"
    ENRICHMENT_CONTEXT_MODEL_CONFIGURATION_VERSION = f"{ENRICHMENT_SILVER_PARSED_COLUMN}.{ENRICHMENT_CONTEXT_COLUMN}.model_configuration.version"
    ENRICHMENT_CONTEXT_ENRICHMENT_INPUT_PATIENT_ID = f"{ENRICHMENT_SILVER_PARSED_COLUMN}.{ENRICHMENT_CONTEXT_COLUMN}.enrichment_input.patient_id"
    ENRICHMENT_CONTEXT_ENRICHMENT_INPUT_METADATA = f"{ENRICHMENT_SILVER_PARSED_COLUMN}.{ENRICHMENT_CONTEXT_COLUMN}.enrichment_input.metadata"
    ENRICHMENT_OUTPUT_VALUE = f"{ENRICHMENT_SILVER_OUTPUTS_COLUMN}.value"
    ENRICHMENT_OUTPUT_CONFIDENCE_SCORE = f"{ENRICHMENT_SILVER_OUTPUTS_COLUMN}.confidence_score"
    ENRICHMENT_OUTPUT_DESCRIPTION = f"{ENRICHMENT_SILVER_OUTPUTS_COLUMN}.description"
    ENRICHMENT_PARSED_OUTPUTS = f"{ENRICHMENT_SILVER_PARSED_COLUMN}.{ENRICHMENT_SILVER_OUTPUTS_COLUMN}"
    ENRICHMENT_PARSED_VALUE = f"{ENRICHMENT_SILVER_PARSED_COLUMN}.value"
    ENRICHMENT_PARSED_TYPE = f"{ENRICHMENT_SILVER_PARSED_COLUMN}.type"
    ENRICHMENT_PARSED_CONTEXT_ID = f"{ENRICHMENT_SILVER_PARSED_COLUMN}.{ENRICHMENT_CONTEXT_COLUMN}.enrichment_context_id"
    ENRICHMENT_PARSED_GENERATION_ID = f"{ENRICHMENT_SILVER_PARSED_COLUMN}.enrichment_generation_id"
    ENRICHMENT_PARSED_DEFINITION_ID = f"{ENRICHMENT_SILVER_PARSED_COLUMN}.enrichment_definition_id"
    
    #Text columns and json paths
    ENRICHMENT_SILVER_TEXT_VALUE_COLUMN = "value"
    ENRICHMENT_SILVER_TEXT_DOMAIN_COLUMN  = "domain"
    ENRICHMENT_SILVER_TEXT_REASONING_COLUMN  = "reasoning"
    ENRICHMENT_SILVER_TEXT_EVIDENCE_COLUMN  = "evidence"
    ENRICHMENT_SILVER_TEXT_TERMINOLOGY_COLUMN  = "terminology"
    ENRICHMENT_PARSED_DOMAIN = f"{ENRICHMENT_SILVER_PARSED_COLUMN}.domain"
    ENRICHMENT_PARSED_REASONING = f"{ENRICHMENT_SILVER_PARSED_COLUMN}.reasoning"
    ENRICHMENT_PARSED_EVIDENCE = f"{ENRICHMENT_SILVER_PARSED_COLUMN}.evidence"
    ENRICHMENT_PARSED_TERMINOLOGY = f"{ENRICHMENT_SILVER_PARSED_COLUMN}.terminology"
    
    #Object columns and json paths
    ENRICHMENT_SILVER_OBJECT_VALUE_COLUMN = "value"
    ENRICHMENT_SILVER_OBJECT_TYPE_COLUMN = "type"
    ENRICHMENT_SILVER_OBJECT_DESCRIPTION_COLUMN = "description"
    ENRICHMENT_SILVER_OBJECT_REASONING_COLUMN  = "reasoning"
    ENRICHMENT_SILVER_OBJECT_EVIDENCE_COLUMN  = "evidence"
    ENRICHMENT_PARSED_DESCRIPTION = f"{ENRICHMENT_SILVER_PARSED_COLUMN}.description"
    
    #Embedding columns and json paths
    ENRICHMENT_SILVER_EMBEDDING_VECTOR_COLUMN  = "vector"
    ENRICHMENT_PARSED_VECTOR = f"{ENRICHMENT_SILVER_PARSED_COLUMN}.vector"
    
    #Segmentation 2D columns and json paths
    ENRICHMENT_SEGMENTATION_RLE_TYPE = "rle"
    ENRICHMENT_SEGMENTATION_CLASS_LABEL_TYPE = "class_label"
    ENRICHMENT_SEGMENTATION_BOUNDING_BOX_TYPE = "bounding_box"
    
    ENRICHMENT_SILVER_SEGMENTATION_HEIGHT_COLUMN  = "height"
    ENRICHMENT_SILVER_SEGMENTATION_WIDTH_COLUMN   = "width"
    ENRICHMENT_SILVER_SEGMENTATION_DEPTH_COLUMN   = "depth"
    ENRICHMENT_SILVER_SEGMENTATION_METADATA_COLUMN = "segmentation_metadata"
    ENRICHMENT_SILVER_SEGMENTATION_TYPE_COLUMN    = "segmentation_type"
    ENRICHMENT_SILVER_SEGMENTATION_RLE_MASK_COLUMN = "rle_segmentation_mask"
    ENRICHMENT_SILVER_SEGMENTATION_FILE_REF_MASK_COLUMN = "file_ref_segmentation_mask"
    ENRICHMENT_SILVER_SEGMENTATION_BOUNDING_BOX_COLUMN  = "bounding_box"
    ENRICHMENT_SILVER_SEGMENTATION_CLASS_LABEL_COLUMN   = "class_label"
    ENRICHMENT_SILVER_SEGMENTATION_BACKGROUND_COLUMN    = "background"
    ENRICHMENT_SILVER_SEGMENTATION_VALUE_COLUMN         = "value"
    
    ENRICHMENT_PARSED_HEIGHT = f"{ENRICHMENT_SILVER_PARSED_COLUMN}.height"
    ENRICHMENT_PARSED_WIDTH = f"{ENRICHMENT_SILVER_PARSED_COLUMN}.width"
    ENRICHMENT_PARSED_DEPTH = f"{ENRICHMENT_SILVER_PARSED_COLUMN}.depth"
    ENRICHMENT_PARSED_SEGMENTATION_MASK_METADATA = f"{ENRICHMENT_SILVER_PARSED_COLUMN}.metadata"
    ENRICHMENT_PARSED_BOUNDING_BOX_METADATA = f"{ENRICHMENT_SILVER_PARSED_COLUMN}.metadata"
    ENRICHMENT_PARSED_MASK_TYPE = f"{ENRICHMENT_SILVER_PARSED_COLUMN}.segmentation_type"
    ENRICHMENT_PARSED_RLE_MASK = f"{ENRICHMENT_SILVER_PARSED_COLUMN}.segmentation_mask.rle"
    ENRICHMENT_PARSED_CLASS_LABEL_MASK = f"{ENRICHMENT_SILVER_PARSED_COLUMN}.segmentation_mask.class_label"
    ENRICHMENT_PARSED_BACKGROUND = f"{ENRICHMENT_SILVER_PARSED_COLUMN}.segmentation_mask.background"
    ENRICHMENT_PARSED_FILE_REF_MASK = f"{ENRICHMENT_SILVER_PARSED_COLUMN}.file_ref_segmentation_mask"
    ENRICHMENT_PARSED_BOUNDING_BOX = f"{ENRICHMENT_SILVER_PARSED_COLUMN}.bounding_box"
    
    ENRICHMENT_SILVER_CHECKPOINT_FOLDER = "ai_enrichments_silver"
    ENRICHMENT_BRONZE_CHECKPOINT_FOLDER = "ai_enrichments_bronze"
    ENRICHMENT_COMMON_SCHEMA_NAME = "common"
    ENRICHMENT_SUFFIX = "Enrichments"
    DEFAULT_AI_ENRICHMENT_LANDING_FOLDER = "AIEnrichments"

    # Enrichment Types
    ENRICHMENT_TYPE_TEXT = "text"
    ENRICHMENT_TYPE_OBJECT = "object"
    ENRICHMENT_TYPE_EMBEDDING = "embedding"
    ENRICHMENT_TYPE_SEG2D = "segmentation2d"
    ENRICHMENT_TYPE_SEG3D = "segmentation3d"
    
    # Activity Names
    ENRICHMENT_BRONZE_INGESTION_ACTIVITY_NAME = "ai-enrichment-bronze-ingestion"
    ENRICHMENT_SILVER_INGESTION_ACTIVITY_NAME = "ai-enrichment-silver-ingestion"
    ENRICHMENT_METADATA_STORE_PATH_KEY = "metadatastore_tables_path"

    # Client Manager
    DEFAULT_TOTAL_RETRIES = 3
    DEFAULT_DELAY_MULTIPLIER = 1
    DEFAULT_MIN_BACKOFF = 2
    DEFAULT_MAX_BACKOFF = 60
    DEFAULT_RETRY_ON_STATUS_CODES = [500, 502, 503, 504, 429]
    DEFAULT_REQUEST_TIMEOUT = 30
    
    # Schema Definitions
    AI_ENRICHMENT_VIEW_SCHEMA = StructType([
        StructField("name", StringType(), nullable=False),
        StructField("description", StringType(), nullable=True),
        StructField("definition", StringType(), nullable=True),
        StructField("id", StringType(), nullable=False)
    ])

    AI_ENRICHMENT_SCHEMA = StructType([
        StructField("name", StringType(), nullable=False),
        StructField("description", StringType(), nullable=True),
        StructField("definition", StringType(), nullable=True),
        StructField("id", StringType(), nullable=False)
    ])

    AI_ENRICHMENT_MATERIALIZED_VIEW_SCHEMA = StructType([
        StructField("view_id", StringType(), nullable=False),
        StructField("reference_materialized_view_path", StringType(), nullable=True),
        StructField("name", StringType(), nullable=False),
        StructField("id", StringType(), nullable=False)
    ])

    AI_ENRICHMENT_GENERATED_SCHEMA = StructType([
        StructField("materialize_view_id", StringType(), nullable=False),
        StructField("input_name", StringType(), nullable=True),
        StructField("name", StringType(), nullable=True),
        StructField("id", StringType(), nullable=False)
    ])

    AI_ENRICHMENT_CONTEXT_SCHEMA = StructType([
        StructField("enrichment_context_id", StringType(), nullable=False),
        StructField("context", StringType(), nullable=False),
        StructField("enrichment_generation_id", StringType(), nullable=True),
        StructField("id", StringType(), nullable=False),
        StructField("msftModifiedDatetime", TimestampType(), True),
        StructField("msftCreatedDatetime", TimestampType(), True)
    ])

    AI_ENRICHMENT_OBJECT_TYPE_SCHEMA = StructType([
            StructField("context", StructType([
                StructField("enrichment_context_id", StringType(), True),
                StructField("model_configuration", StructType([
                    StructField("api_endpoint", StringType(), True),
                    StructField("api_version", StringType(), True),
                    StructField("version", StringType(), True),
                    StructField("name", StringType(), True),
                    StructField("fhir_version", StringType(), True),
                ]), True),
                StructField("enrichment_input", StructType([
                    StructField("patient_id", StringType(), True),
                    StructField("metadata", StructType([
                        StructField("document_id", StringType(), True),
                    ]), True),
                    StructField("text_file_references", ArrayType(StructType([
                        StructField("id", StringType(), True),
                        StructField("content", StringType(), True),
                        StructField("section", StringType(), True),
                    ])), True),
                    StructField("image_file_references", ArrayType(StringType()), True),
                ]), True),
            ]), True),
            StructField("outputs", ArrayType(StructType([
                StructField("confidence_score", StringType(), True),
                StructField("description", StringType(), True),
                StructField("type", StringType(), True),
                StructField("value", StructType([
                    StructField("reasoning", StringType(), True),
                    StructField("evidence", ArrayType(StringType()), True),
                    StructField("type", StringType(), True),
                    StructField("value", ArrayType(StringType(), True), True),
                ]), True),
            ])), True),
            StructField("enrichment_generation_id", StringType(), True),
        ])

    AI_ENRICHMENT_FLAT_FHIR_OBJECT_SCEHMA = StructType([
        StructField("run_id", StringType(), True),
        StructField("enrichment_definition_id", StringType(), True),
        StructField("resource_type", StringType(), True),
        StructField("source_file", StringType(), True),
        StructField('resource',  StringType(), True)
    ])
    
    
    # Default temperature for generating text (controls randomness)
    DEFAULT_TEMPERATURE = 0

    # Default top-p value for generating text (controls diversity via nucleus sampling)
    DEFAULT_TOP_P = 0.95

    # Default frequency penalty for generating text (penalizes new tokens based on their frequency)
    DEFAULT_FREQUENCY_PENALTY = 0

    # Default presence penalty for generating text (penalizes new tokens based on their presence)
    DEFAULT_PRESENCE_PENALTY = 0

    # Default stop token for generating text (determines when to stop generating text)
    DEFAULT_STOP = None

    # Default stream mode for generating text (determines if the response should be streamed)
    DEFAULT_STREAM = False

    # Default model name for generating text
    MODEL_NAME = "gpt-4o"

    # System message for the AI assistant (provides context for the assistant)
    SYSTEM_MESSAGE = "You are an AI assistant that helps people find information in JSON format."

    # Default OpenAI tool for JSON formatting
    DEFAULT_OPEN_AI_TOOL_JSON = "analysis_schema_json"
    
    # Type of assistant (e.g., code interpreter)
    ASSISTANT_TYPE = "code_interpreter"
    
    OPENAI_DATA_INPUT_SCHEMA_FORMAT_ERROR = "Invalid schema format for input json"