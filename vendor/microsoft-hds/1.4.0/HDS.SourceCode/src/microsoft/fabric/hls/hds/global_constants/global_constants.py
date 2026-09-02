import logging
from pyspark.sql.types import StructType, StructField, IntegerType, StringType, DateType, TimestampType, BooleanType


class GlobalConstants:
    # DB Constants
    OMOP_FHIR_POC_DB: str = "omoponfhir_poc_db"

    # OMOP Id Mapping table
    OMOP_ID_MAPPING_TABLE: str = "omop_id_mappings"
    OMOP_ID_MAPPING_TABLE_RESOURCE_TYPE_FIELD: str = "RESOURCE_TYPE"
    OMOP_ID_MAPPING_TABLE_EXTERNAL_ID_FIELD: str = "EXTERNAL_ID"
    OMOP_ID_MAPPING_TABLE_SOURCE_ID_FIELD: str = "SOURCE_ID"
    OMOP_ID_MAPPING_TABLE_ADRM_ID_FIELD: str = "ADRM_ID"

    # Concept table
    CONCEPT_TABLE: str = "concept"
    CONCEPT_TABLE_START_DATE_FIELD: str = "valid_start_date"
    CONCEPT_TABLE_END_DATE_FIELD: str = "valid_end_date"
    CONCEPT_TABLE_CONCEPT_ID_FIELD: str = "concept_id"
    CONCEPT_TABLE_CONCEPT_CODE_FIELD: str = "concept_code"
    CONCEPT_TABLE_CONCEPT_NAME_FIELD: str = "concept_name"
    CONCEPT_TABLE_STANDARD_CONCEPT_FIELD: str = "standard_concept"
    CONCEPT_TABLE_DOMAIN_ID_FIELD: str = "domain_id"

    # Concept relationship table
    CONCEPT_RELATIONSHIP_TABLE: str = "concept_relationship"
    CONCEPT_RELATIONSHIP_TABLE_START_DATE_FIELD: str = "valid_start_date"
    CONCEPT_RELATIONSHIP_TABLE_END_DATE_FIELD: str = "valid_end_date"
    CONCEPT_RELATIONSHIP_TABLE_RELATION_ID_FIELD: str = "relationship_id"
    CONCEPT_RELATIONSHIP_TABLE_CONCEPT_ID1_FIELD: str = "concept_id_1"
    CONCEPT_RELATIONSHIP_TABLE_CONCEPT_ID2_FIELD: str = "concept_id_2"

    # Omop fhir vocab mapping table
    VOCAB_MAPPING_TABLE: str = "fhiromopvocabmapping"
    VOCAB_MAPPING_TABLE_FHIR_FIELD: str = "fhir_uri"
    VOCAB_MAPPING_TABLE_DOMAIN_FIELD: str = "domain"
    VOCAB_MAPPING_TABLE_VOCAB_ID_FIELD: str = "vocabulary_id"

    # Folder paths
    FILES_FOLDER_FABRIC = "Files"
    BRONZE_CONTAINER = "bronze"
    PROCESSING_STATUS_FOLDER = "processing_status"
    FHIR_2_OMOP_FOLDER = "fhir_2_omop"
    TO_PROCESS_FOLDER = "to_process"
    PROCESS_FOLDER = "Process"
    HEALTHCARE_DATA_MANAGER_CONFIGURATION_CONTAINER = "datamanager"
    FHIR_TO_OMOP_CONFIGURATION_FOLDER = "fhir_2_omop"
    FLATTEN_CONFIG_FOLDER = "flatten"
    TA4H_CONFIG_FOLDER = "ta4h"
    DTT_CONFIG_FOLDER = "dtt"
    DTT_STATE_DB = "dtt_state_db"
    INTERNAL_FOLDER = "_internal"
    PACKAGES_FOLDER = "packages"
    SCHEMA_CONFIGURATION_FOLDER = "schema"
    TRANSFORMATION_CONFIGURATION_FOLDER = "transformation"
    CLAIMS_CMS_CCLF_FOLDER = "claims_cms_cclf"
    FLATTEN_CONFIG_NAME = "flatten_config.json"
    DMF_ADAPTER_FILE = "dmfAdapter.json"
    DB_TARGET_SCHEMA = "dbTargetSchema.json"
    DB_TARGET_SCHEMA_CONFIG = "dbTargetSchemaConfig.json"
    DB_SEMANTICS_CONFIG = "dbSemanticsConfig.json"
    DB_SEMANTICS = "dbSemantics.json"
    SILVER_CONTAINER = "silver"
    GOLD_CONTAINER = "gold"
    OMOP_DB_FOLDER = "omop_db"
    FLATTENED_DATA_FOLDER = "flattened_data"
    FHIR_4 = "fhir4"
    CLAIMS_FOLDER = "Claims"
    CCLF_FOLDER = "CCLF"
    MEDICAL_IMAGING_FOLDER = "Imaging"
    DICOM_FOLDER = "DICOM"
    IMAGING_OPERATIONS_FOLDER = "OPERATIONS"
    CLINICAL_FOLDER = "Clinical"
    CLAIMS_CCLF_FOLDER = "claims_data_ingestions"
    CLAIMS_INGESTION_FOLDER = "claims_data_ingestions"
    SOURCE_TYPE="source_type"
    VALIDATION_FOLDER = "validation"
    VALIDATION_CONFIG_FILE = "validationConfig.json"
    FILE_ORCHESTRATION_FOLDER = "file_orchestration"
    IDM_DMF_ADAPTER_FILE = "adapter.json"
    IDM_DB_TARGET_SCHEMA = "dbTargetSchema.json"
    IDM_DB_TARGET_SCHEMA_CONFIG = "dbConfig.json"
    IDM_DB_SEMANTICS_CONFIG = "dbSemanticsConfig.json"
    IDM_DB_SEMANTICS = "dbSemantics.json"
    IDM_FOLDER = "idm"
    CMA_FOLDER = "cma"
    CMA_CLINICAL = "clinical"
    IDM_RMT_REFERENCE_TABLES_FOLDER = "reference_tables"
    IDM_RMT_REFERENCE_TABLES_MAPPING_FOLDER = "mapping"
    IDM_RMT_REFERENCE_TABLES_DATA_FOLDER = "data"
    IDM_RMT_REFERENCE_TABLES_DATA_COMMON_FOLDER = "Common"
    IDM_RMT_REFERENCE_TABLES_DATA_HEALTHCARE_FOLDER = "Healthcare"
    IDM_RMT_REFERENCE_TABLES_DOMAIN_FOLDER = "HLC-IDM"

    # SDOH
    SDOH_NA = "NA"
    SDOH_FOLDER = "sdoh"
    SDOH_DMF_ADAPTER_FILE = "adapter.json"
    SDOH_DB_TARGET_SCHEMA = "dbTargetSchema.json"
    SDOH_DB_TARGET_SCHEMA_CONFIG = "dbConfig.json"
    SDOH_DB_SEMANTICS_CONFIG = "dbSemanticsConfig.json"
    SDOH_DB_SEMANTICS = "dbSemantics.json"
    SDOH_RMT_REFERENCE_TABLES_FOLDER = "reference_tables"
    SDOH_RMT_REFERENCE_TABLES_MAPPING_FOLDER = "mapping"
    SDOH_RMT_REFERENCE_TABLES_DATA_FOLDER = "data"
    SDOH_RMT_REFERENCE_TABLES_DATA_COMMON_FOLDER = "Common"
    SDOH_RMT_REFERENCE_TABLES_DATA_HEALTHCARE_FOLDER = "Healthcare"
    SDOH_RMT_REFERENCE_TABLES_DOMAIN_FOLDER = "HLC-SDOH"
    SDOH_DATA_TABLES_MAPPING = "sdohDataTablesMapping.json"
    SDOH_META_DATA_TABLES_MAPPING = "sdohMetaDataTablesMapping.json"
    SDOH_META_DATA_TABLE = "SdohDataSetMetadata"
    SDOH_LAYOUT_TABLE = "SdohLayout"
    SDOH_BRONZE_TABLE_NAME = "SdohDatasets"
    SDOH_DEFAULT_BRONZE_INGESTION_PATH = "SDOH"
    STREAMING_CHECKPOINT_FOLDER = "streaming_checkpoint_data"
    DEFAULT_SDOH_BRONZE_INGESTION_RETRY_COUNT = 3
    PARAMETERS_CONFIGS_FOLDER = "system-configurations"
    PARAMETERS_DEPLOYMENT_CONFIG = "deploymentParametersConfiguration.json"
    
    #Generic DTT Service
    DTT_DMF_ADAPTER_FILE = "adapter.json"
    DTT_TRANSFORMATION_EVENT = "Failed to transform and ingest data in to lakehouse using DTTWorkflow"

    # FHIR Export
    FHIR_EXPORT_MAX_POLLING_DAYS = 3
    FUNCTION_URL_SECRET_NAME = "FunctionAppEndpoint"
    AZURE_FUNCTION_URL_FORMAT = "{function_url}/api/Run_Export/{run_id}?code={code}"

    # Silver
    DEFAULT_SILVER_LAKEHOUSE_NAME = "silver"
    DEFAULT_SILVER_UNIQUE_COLUMNS: list = ["id"]
    DEFAULT_SOURCE_MODIFIED_ON_COLUMN: str = "meta_lastUpdated"
    DEFAULT_SILVER_MODIFIED_DATE_COL: str = "msftModifiedDatetime"
    DEFAULT_SILVER_FHIR_TABLE_MSFT_SOURCE_SYSTEM_COL: str = "msftSourceSystem"
    DEFAULT_SILVER_FHIR_TABLE_MSFT_CREATED_DATE_COL: str = "msftCreatedDatetime"
    DEFAULT_SILVER_FHIR_TABLE_MSFT_FILE_PATH_COL: str = "msftFilePath"
    DEFAULT_NUMBER_OF_FILES_PER_TRIGGER_SILVER = 1000
    DEFAULT_NUMBER_OF_BYTES_PER_TRIGGER_SILVER = 1000000000
    DEFAULT_NUMBER_OF_MAX_STREAMING_QUERIES_SILVER = 3
    DEFAULT_SILVER_FHIR_IDENTIFIER_COL: str = "identifier"

    # Bronze
    DEFAULT_BRONZE_LAKEHOUSE_NAME = "bronze"
    DEFAULT_NUMBER_OF_FILES_PER_TRIGGER_BRONZE = 1000
    DEFAULT_NUMBER_OF_BYTES_PER_TRIGGER_BRONZE = 1000000000
    DEFAULT_NUMBER_OF_MAX_STREAMING_QUERIES_BRONZE = 1
    DEFAULT_LANDINGZONE_SOURCE_PATTERN = "Process/Clinical/FHIR-NDJSON"
    DEFAULT_BRONZE_CREATED_DATE_COL: str = "createdDatetime"
    DEFAULT_ONE_LAKE_ENDPOINT: str = "onelake.dfs.fabric.microsoft.com"
    DEFAULT_BRONZE_FHIR_TABLE_NAME: str = "ClinicalFhir"
    DEFAULT_BRONZE_FHIR_TABLE_PARTITION_COLS: str = ["resourceType"]
    RESOURCE_TYPE_HIVE_DEFAULT_PARTITION: str = "resourceType=__HIVE_DEFAULT_PARTITION__"
    DEFAULT_DELTA_LOG_RETENTION_DURATION: str = "90 days"
    DEFAULT_DELTA_DELETED_FILE_RETENTION_DURATION: str = "90 days"
    DEFAULT_FHIR_NDJSON_FILE_EXTENSION: str = "ndjson"

    DEFAULT_BRONZE_FHIR_TABLE_ID_COL: str = "id"
    DEFAULT_BRONZE_FHIR_TABLE_RESOURCE_TYPE_COL: str = "resourceType"
    DEFAULT_BRONZE_FHIR_TABLE_SOURCE_SYSTEM_COL: str = "sourceSystem"
    DEFAULT_BRONZE_FHIR_TABLE_FILE_PATH_COL: str = "filePath"
    DEFAULT_BRONZE_FHIR_TABLE_RESOURCE_CONTENT_COL: str = "fhirContent"
    DEFAULT_BRONZE_FHIR_TABLE_SOURCE_MODIFIED_ON_COL: str = "lastUpdated"

    BRONZE_PARSED_RESOURCE_COL_NAME: str = "parsed_resource"
    BRONZE_ORIGINAL_SRC_PATH_COL_NAME: str = "sourceFilePath"
    
    DEFAULT_BRONZE_FHIR_SOURCE_META_LASTUPDATED_COL: str = "meta.lastUpdated"

    DROP_FOLDER = "Ingest"
    PROCESS_FOLDER = "Process"
    EXTERNAL_FOLDER = "External"
    FAILED_FOLDER = "Failed"
    INVENTORY_FOLDER = "Inventory"

   # spark config keys
    SPARK_KEY_VAULT_NAME = "spark.key_vault_name"
    SPARK_DTT_APP_INSIGHTS_CONNECTION_STRING = "spark.dtt.application_insights.instrumentation_key"
    SPARK_ENABLE_HDS_LOGS = "spark.hds.enable_hds_logs"
    SPARK_PARQUET_DATE_REBASE_MODE_IN_WRITE_KEY = "spark.sql.parquet.int96RebaseModeInWrite"
    SPARK_PARQUET_DATETIME_REBASE_MODE_IN_WRITE_KEY = "spark.sql.parquet.datetimeRebaseModeInWrite"
    SPARK_ENABLE_HDS_COLLECT_METRICS = "spark.hds.enable_hds_collect_metrics"
    SPARK_DELTA_LOG_RETENTION_DURATION_PROPERTY: str = "delta.logRetentionDuration"
    SPARK_DELTA_DELETED_FILE_RETENTION_DURATION_PROPERTY: str = "delta.deletedFileRetentionDuration"
    
    #Claims_Cms_Cclf business events table constants
    INFO = "Info"
    CMSCCLF_CLAIMS_LANDINGZONE_TO_DELTATABLE_INGESTION_NOTEBOOK :str = "claims_cclf_landing_zone_delta_tables_ingestion"
    CMS_CCLF_DROP_FOLDER_TO_DELTA_TABLES_CHECKPOINT_FOLDER: str = "CmsCclfDropFolderToDeltaTablesCheckpointFolder"
    RECORD_INSERTION_SUCCESS = "Successfully inserted: {count} records in: {target_delta_table} delta table."
    CMSCCLF_CLAIMS_DELTA_TABLE_RECORD_INSERTION_SUCCESS_MESSAGE  :str = "Cms cclf delta table record insertion successful"
    CMSCCLF_CLAIMS_MAX_FILE_SIZE_EXCEED:str =  "CMS_CCLF_MAX_FILE_SIZE_EXCEED"
    CMSCCLF_CLAIMS_MAX_FILE_SIZE_EXCEED_EXCEPTION_MESSAGE:str = "File size exceeds the maximum limit of {max_file_size} MB"
    CMSCCLF_CLAIMS_CURRENT_LINE_ITEM_LENGTH_NOT_MATCHING: str = "Cms_CCLF_CURRENT_LINE_ITEM_LENGTH_NOT_MATCHING"
    CMSCCLF_CLAIMS_CURRENT_LINE_ITEM_LENGTH_NOT_MATCHING_MESSAGE: str = "{value} of record did not match the expected length of: {file_extension}"
    CMSCCLF_CLAIMS_INVALID_FILE : str = "CMS_CCLF_INVALID_FILE" 
    CMSCCLF_CLAIMS_INVALID_FILE_EXCEPTION_MESSAGE : str = "Invalid cms cclf file uploaded" 
    CMSCCLF_CLAIMS_CCLF_FHIR_CONVERSION: str = "claims_cclf_fhir_conversion"
    CMSCCLF_CLAIMS_SUCCESS_GENERATE_NDJSON_AND_SAVE: str = "Successfully generated ndjson and saved to the target folder"
    CMSCCLF_CLAIMS_NO_RECORS_GENERATE_NDJSON_AND_SAVE: str = "No records to generate ndjson and save to the target folder"
    CMSCCLF_CLAIMS_FAILED_GENERATE_NDJSON_AND_SAVE: str = "Failed to generate ndjson and save to the target folder" 
    CMSCCLF_CLAIMS_FAILED_EXECUTE_NDJSON_GENERATION: str = "Failed to execute ndjson generation from the source table"
    
    CLAIMS_GENERATE_NDJSON_AND_SAVE_EVENT: str = "Generate NDJSON and Save method - "

    # base_custom_table_creator business events logging constants
    BASE_CUSTOM_TABLE_CREATOR_SERVICE = "base_custom_table_creator_service"
    BE_EVENT_INIT_FAILED = "Class:BaseCustomTableCreator. Method:__init__. Step:Class instantiation failed."
    BE_EVENT_READ_STREAM_FAILED = "Class:BaseCustomTableCreator. Method:read_stream. Step:Read stream failed on delta table."
    BE_EVENT_WRITE_STREAM_FAILED = "Class:BaseCustomTableCreator. Method:write_stream. Step:Write stream failed on delta table."
    
    # DAX Entities
    DEFAULT_DAX_TARGET_BRONZE_TABLE_NAME = "DaxCopilotData"
    DEFAULT_DAX_TRANSCRIPT_SILVER_TABLE_NAME = "DaxTranscripts"
    DEFAULT_DAX_FILES_PATTERN = "*.json"
    DAX_TRANSCRIPT_RESOURCE_TYPE = "Transcripts"
    DEFAULT_DAX_SILVER_PREFIX = "Dax"
    DEFAULT_DAX_COPILOT_DATA_FOLDER= "External/DaxCopilot/dax_copilot_data"
    
    # DAX Bronze Ingestion
    DAX_BRONZE_FILE_CONTENT_COLUMN = "fileContent"
    DAX_BRONZE_VALUE_COLUMN = "value"
    DAX_BRONZE_PROCESS_TIME_COLUMN = "process_time"
    DAX_BRONZE_FULL_FILE_PATH_COLUMN = "filePath"
    DAX_BRONZE_FILENAME_NO_EXTENSION_COLUMN = "filename_noextension"
    DAX_BRONZE_FILENAME_REGEX = r"([^/]+)$"
    DAX_BRONZE_FILENAME_NO_EXTENSION_REGEX = r"^(.+)\.([^.]+)$"
    DAX_BRONZE_PARENT_FOLDER_COLUMN = "parent_folder"
    DAX_BRONZE_FILE_TYPE_COLUMN = "fileType"
    DAX_BRONZE_FILE_TYPE_REGEX = r"/([^/]+)/[^/]+$"
    DAX_BRONZE_SOURCE_SYSTEM_COLUMN = "sourceSystem"
    DAX_BRONZE_SOURCE_SYSTEM_REGEX = r"External/([^/]+/[^/]+)"
    
    # DAX Silver Ingestion
    DAX_SILVER_TRANSCRIPT_ID_COLUMN = "transcriptId"

    # DAX Service
    DAX_BRONZE_INGESTION_ACTIVITY_NAME = "dax-bronze-ingestion"
    DAX_SILVER_INGESTION_ACTIVITY_NAME = "dax-silver-ingestion"
     
    # to_process file
    TIMESTAMP = "timestamp"
    FLATTEN_STATUS = "flattenStatus"
    STATUS = "status"
    STATUS_DETAIL = "statusDetail"
    ERROR = "error"
    INFO = "info"
    EXCEPTION = "exception"
    
    RESOURCES_TO_TRANSFORM = "resourcesToTransform"
    RESOURCE_TYPE = "resourceType"
    RESOURCE_PATH_TO_FOLDER = "path"
    DTT_STATUS = "dttStatus"

    # token
    STORAGE_AUDIENCE_TYPE = "Storage"
    TOKEN_EXPIRATION_IN_SECONDS = 600

    # Blob Client Lease
    # Anthing more than 60 seconds is throwing HttpResponseError
    LEASE_EXPIRATION_IN_SECONDS = 60
    LEASE_RENEWAL_IN_SECONDS = 30

    # text analytics
    DOCUMENT_LIMIT = 1000
    RETRY_COUNT = 3
    ENABLE_TEXT_ANALYTICS_LOGS = False
    
    OPENAI_KEY_SECRET_NAME = "OpenAIServiceKey"
    OPENAI_API_ENDPOINT_SECRET_NAME = "OpenAIServiceEndpoint"

    # resource folder names
    DOCUMENT_REFERENCE_CONTENT_FOLDER = "documentreferencecontent"

    # NLP preview resource type to analyze
    DOCUMENT_REFERENCE_CONTENT_RESOURCE = "DocumentReferenceContent"


    # logging
    APPINSIGHTS_INGESTION_ENDPOINT_KEY_SECRET_NAME = "AppInsightsIngestionEndpointKey"
    DATA_MANAGER_LOGGER: str = "Healthcaredatasolutions"
    FHIR_TO_OMOP: str = "fhirtoomop"
    LOGGING_LEVEL: int = logging.INFO
    DEBUG_LOGGING_LEVEL: int = logging.DEBUG
        
    DICOM_IMAGING: str = "DicomImaging"

    SDOH_BRONZE_INGESTION: str = "SdohBronzeIngestion"

    CCLF: str = "CCLF"  
    
    DATA_MANAGER_DEPLOYMENT: str = "HealthcaredatasolutionsDeployment"
    DATA_MANAGER_BRONZE_INGESTION: str = "HealthcaredatasolutionsBronzeIngestion"
    DATA_MANAGER_SILVER_INGESTION: str = "HealthcaredatasolutionsSilverIngestion"
    DATA_MANAGER_CUSTOM_SILVER_INGESTION: str = "HealthcaredatasolutionsCustomSilverIngestion"
    DATA_MANAGER_OMOP_INGESTION: str = "HealthcaredatasolutionsOMOPIngestion"
    DATA_MANAGER_FHIR_EXPORT: str = "HealthcaredatasolutionsFHIRExport"
    DATA_MANAGER_PATIENT_OUTREACH_GOLD_INGESTION: str = "HealthcaredatasolutionsPatientOutreachGoldIngestion"
    DATA_MANAGER_IDM_SILVER_INGESTION: str = "HealthcaredatasolutionsIDMSilverIngestion"
    DATA_MANAGER_SDOH_SILVER_INGESTION: str = "HealthcaredatasolutionsSDOHSilverIngestion"
    DATA_MANAGER_DAX_BRONZE_INGESTION: str = "HealthcaredatasolutionsDaxBronzeIngestion"
    DATA_MANAGER_DAX_SILVER_INGESTION: str = "HealthcaredatasolutionsDaxSilverIngestion"
    
    DATA_MANAGER_CM_ANALYTICS_GOLD_INGESTION: str = "HealthcaresolutionsCMAnalyticsGoldIngestion"
    DATA_MANAGER_AI_ENRICHMENT_BRONZE_INGESTION: str = "HealthcaresolutionsAIENRICHMENTBronzeIngestion"
    DATA_MANAGER_AI_ENRICHMENT_SILVER_INGESTION: str = "HealthcaresolutionsAIENRICHMENTSilverIngestion"
    DATA_MANAGER_AI_ENRICHMENT_EXECUTION: str = "HealthcaresolutionsAIEnrichmentExecution"
    DATA_MANAGER_AI_ENRICHMENT_METADATA: str = "HealthcaresolutionsAIEnrichmentsMetaDataService"
    DATA_MANAGER_AI_TA4H_ENRICHMENT_EXECUTION: str = "HealthcaresolutionsAIEnrichmentTA4HExecution"
    DATA_MANAGER_AI_MII_ENRICHMENT_EXECUTION: str = "HealthcaresolutionsAIEnrichmentMedImageInsightsExecution"
    DATA_MANAGER_AI_CONVERSATIONALDATA_ENRICHMENT_EXECUTION: str = "HealthcaresolutionsAIEnrichmentConversationalDataExecution"
    DATA_MANAGER_BUSINESS_EVENTS_INGESTION: str = "HealthcaredatasolutionsBusinessEventsIngestion"
 
    DATA_MANAGER_AI_MIP_ENRICHMENT_EXECUTION="HealthcaresolutionsAIEnrichmentMedImageParseExecution" 
     
     
    DEFAULT_BRONZE_LAKEHOUSE_NAME = "bronze"
    DEFAULT_SILVER_LAKEHOUSE_NAME = "silver"
    DEFAULT_OMOP_LAKEHOUSE_NAME = "omop"
    DATA_MANAGER_CONFIGURATION_FOLDER_ROOT = "DMHConfiguration"
    DATA_MANAGER_CHECKPOINT_FOLDER_ROOT = "DMHCheckpoint"
    DMF_CONFIG_PATH = "dmfConfig.json"
    RMT_CONFIG_PATH = "rmtConfig.json"
    ENV_CONFIG_PATH = "environment.json"
    DATA_MANAGER_SAMPLE_DATA_FOLDER_ROOT = "DMHSampleData"

    DEFAULT_REFERENCE_DATA_ROOT_FOLDER = "ReferenceData"
    OMOP_CONFIG_FOLDER = "omop"
    VOCAB_CHECKPOINT_FOLDER = "vocab"
    CLINICAL_VOCAB_DATA_PATH = "Clinical/OMOP/Vocab-HDS"
    SCRIPTS_FOLDER = "scripts"
    OMOP_VERSION_54 = "5_4"
    
    # SDOH Business events Constants
    SDOH_BRONZE_INGESTION_ACTIVITY_NOTEBOOK = "sdoh_bronze_ingestion"
    SDOH_SILVER_INGESTION_ACTIVITY_NOTEBOOK = "sdoh_silver_ingestion"
    SDOH_MOVE_FROM_DROP_TO_PROCESS_FOLDER = "sdoh move from drop to process folder"
    SDOH_DELTA_TABLE_CREATION_FROM_PROCESS_FOLDER = "sdoh delta table creation from process folder"
    SDOH_READ_EXCEL_FILE_FROM_PATH = "sdoh read excel file from path"
    SDOH_VALIDATE_EXCEL_DATASET_FOR_REQUIRED_SHEETS_AND_COLUMNS = "sdoh validate excel dataset for required sheets and columns"
    SDOH_VALIDATE_CSV_DATASET_FOR_REQUIRED_SHEETS_AND_COLUMNS = "sdoh validate csv dataset for required sheets and columns"
    SDOH_VALIDATE_LOCATION_CONFIGURATION_DATAFRAME = "sdoh validate location configuration dataframe"
    SDOH_VALIDATE_METADATA_DATAFRAME = "sdoh validate metadata dataframe"
    SDOH_VALIDFATE_LAYOUT_DATAFRAME = "sdoh validate layout dataframe"
    SDOH_SUCCESFUL_DELTA_TABLE_CREATION = "sdoh successful dataset ingestion"
    SDOH_FAILED_TO_INGEST_FROM_PROCESS_FOLDER_FOR_EXCEL_FILE = "sdoh failed to ingest from process folder for excel"
    SDOH_FAILED_TO_INGEST_FROM_PROCESS_FOLDER_FOR_CSV_FILE = "sdoh failed to ingest from process folder for csv"
    SDOH_PROCESS_TABLES_FROM_BRONZE_TO_SILVER = "sdoh process tables from bronze to silver"
    SDOH_DTT_WORKFLOW = "sdoh dtt workflow"

    # Validation
    VALIDATION_CONFIG_BRONZE_KEY = "bronze"
    VALIDATION_ERRORS_COL = "validationErrors"
    VALIDATION_WARNINGS_COL = "validationWarnings"
    VALIDATION_EVENT_TYPE = "validation"

    VALIDATION_DF_TOTAL_KEY = "total_records"
    VALIDATION_DF_SUCCESSES_KEY = "successes"
    VALIDATION_DF_ERRORS_KEY = "errors"
    VALIDATION_DF_WARNINGS_KEY = "warnings"
    VALIDATION_METRICS_ACCUMULATOR_KEY = "validationMetricsAccumulator"

    # POA Business Events CONSTANTS
    PATIENT_OUTREACH_BRONZE_TO_SILVER_TRANSFORMATION = "POA bronze to silver transformation"
    PATIENT_OUTREACH_SILVER_TO_GOLD_TRANSFORMATION = "POA silver to gold transformation"
    PATIENT_OUTREACH_GOLD_LAKEHOUSE_NAME = "poa_gold"
    
    # CMA Business events Constants
    CMA_GOLD_INGESTION_ACTIVITY_NOTEBOOK = "cma_gold_ingestion_notebook"
    CMA_TRANSORMATION_AND_INGESTION_TO_GOLD_USING_DTT = "Failed to transform and ingest from Silver to CMA Gold lakehouse using DTTWorkflow"

    # Business Events Table 
    BUSINESS_EVENTS_TABLE = "BusinessEvents"
    BE_ID_COL = "id"
    BE_EVENT_DATE_TIME_COL = "eventDateTime"
    BE_ACTIVE_COL = "active"
    BE_EVENT_TYPE_COL = "eventType"
    BE_ACTIVITY_NAME_COL = "activityName"
    BE_SEVERITY_COL = "severity"
    BE_SOURCE_TABLE_NAME_COL = "sourceTableName"
    BE_TARGET_TABLE_NAME_COL = "targetTableName"
    BE_RUN_ID_COL = "runId"
    BE_TARGET_FILE_PATH_COL = "targetFilePath"
    BE_RECORD_IDENTIFIER_COL = "recordIdentifier"
    BE_MESSAGE_COL = "message"
    BE_EXCEPTION_COL = "exception"
    BE_CUSTOMDIMENSIONS_COL = "customDimensions"
    BE_SOURCE_FILE_PATH_COL = "sourceFilePath"
    BUSINESS_EVENTS_SCHEMA_ROOT_FOLDER = "businessevents"
    BE_RECORD_IDENTIFIER_SOURCE_COL = "recordIdentifierSource"
    BE_SOURCE_LAKEHOUSE_NAME_COL = "sourceLakehouseName"
    BE_TARGET_LAKEHOUSE_NAME_COL = "targetLakehouseName"
    BE_EXCEPTION_COL = "exception"
    BE_CUSTOMDIMENSIONS_COL = "customDimensions"
    BE_CREATEDDATE_COL = "createdDate"
    BE_CREATEDDATETIME_COL = "createdDatetime"

    # Schema and config paths
    DATA_MANAGER_INTERNAL_FOLDER_PATH = f"{DATA_MANAGER_CONFIGURATION_FOLDER_ROOT}/{INTERNAL_FOLDER}"
    DATA_MANAGER_FHIR4_CONFIGURATION_FOLDER_PATH = f"{DATA_MANAGER_INTERNAL_FOLDER_PATH}/{FHIR_4}"
    DATA_MANAGER_FHIR4_TRANSFORMATION_CONFIGURATION_FOLDER_PATH = f"{DATA_MANAGER_FHIR4_CONFIGURATION_FOLDER_PATH}/{TRANSFORMATION_CONFIGURATION_FOLDER}"

    MEDICAL_IMAGING_CONFIG_FOLDER = "medical_imaging"

    PATIENT_OUTREACH_GOLD_CONFIG_PATH = "poagold"
    PATIENT_OUTREACH_RMT_REFERENCE_FOLDER = "reference_tables"
    PATIENT_OUTREACH_RMT_REFERENCE_DATA_FOLDER = "data"
    PATIENT_OUTREACH_RMT_REFERENCE_MAPPING_FOLDER = "mapping"
    PATIENT_OUTREACH_DTT_ADAPTER_FILE = "adapter.json"
    PATIENT_OUTREACH_FOLDER = "poa"
    POA_GOLD_CONFIG_PATH_KEY = "poagold_config_path"

    DEFAULT_PATIENT_OUTREACH_CONFIG_PATH = f"{DATA_MANAGER_INTERNAL_FOLDER_PATH}/{PATIENT_OUTREACH_FOLDER}"
    DEFAULT_PATIENT_OUTREACH_DTT_SECONDARY_LAKE_PATH = f"{DATA_MANAGER_CHECKPOINT_FOLDER_ROOT}/{PATIENT_OUTREACH_FOLDER}/{DTT_CONFIG_FOLDER}/{DTT_STATE_DB}"

    DEFAULT_IDM_CONFIG_PATH=f"{DATA_MANAGER_INTERNAL_FOLDER_PATH}/{IDM_FOLDER}"
    DEFAULT_SDOH_CONFIG_PATH=f"{DATA_MANAGER_INTERNAL_FOLDER_PATH}/{SDOH_FOLDER}"
    
    DEFAULT_DAX_CONFIG_PATH = f"{DATA_MANAGER_INTERNAL_FOLDER_PATH}/dax"
    DEFAULT_DAX_RESOURCES_PATH = f"{DEFAULT_DAX_CONFIG_PATH}/resources"

    DEFAULT_CM_ANALYTICS_CONFIG_CLINICAL_PATH=f"{DATA_MANAGER_INTERNAL_FOLDER_PATH}/{CMA_FOLDER}/{TRANSFORMATION_CONFIGURATION_FOLDER}/{CMA_CLINICAL}"
    DEFAULT_CM_ANALYTICS_CHKPOINT_FOLDER=f"{DATA_MANAGER_CHECKPOINT_FOLDER_ROOT}/{CMA_FOLDER}"
    
    DEFAULT_CM_ANALYTICS_DTT_SECONDARY_LAKE_PATH = f"{DEFAULT_CM_ANALYTICS_CHKPOINT_FOLDER}/{DTT_CONFIG_FOLDER}/{DTT_STATE_DB}"
    DEFAULT_CM_ANALYTICS_DTT_FILE_PATH = f"{DEFAULT_CM_ANALYTICS_CHKPOINT_FOLDER}/{DTT_CONFIG_FOLDER}"
    DEFAULT_CM_ANALYTICS_RMT_MAPPING_FOLDER = "mapping"
    DEFAULT_CM_ANALYTICS_RMT_MAPPING_FOLDER_PATH = f"{DEFAULT_CM_ANALYTICS_CHKPOINT_FOLDER}/{DTT_CONFIG_FOLDER}/{DEFAULT_CM_ANALYTICS_RMT_MAPPING_FOLDER}"
    CM_ANALYTICS_RMT_REFERENCE_FOLDER = "reference_tables"
    CM_ANALYTICS_RMT_REFERENCE_DATA_FOLDER = "data"
    CM_ANALYTICS_DTT_ADAPTER_FILE = "adapter.json"

    DEFAULT_SCHEMA_PATH = f"{DATA_MANAGER_FHIR4_CONFIGURATION_FOLDER_PATH}/schema"

    DEFAULT_FLATTEN_CONFIG_DIR = f"{DATA_MANAGER_FHIR4_TRANSFORMATION_CONFIGURATION_FOLDER_PATH}/{FLATTEN_CONFIG_FOLDER}"
    DEFAULT_FLATTEN_CONFIG_PATH = f"{DEFAULT_FLATTEN_CONFIG_DIR}/{FLATTEN_CONFIG_NAME}"
    DEFAULT_OMOP_CONFIG_PATH = f"{DATA_MANAGER_FHIR4_TRANSFORMATION_CONFIGURATION_FOLDER_PATH}/{OMOP_CONFIG_FOLDER}"
    DEFAULT_OMOP_VOCABULARY_PATH = (
        f"{DEFAULT_REFERENCE_DATA_ROOT_FOLDER}/{CLINICAL_VOCAB_DATA_PATH}"
    )
    
    DEFAULT_VALIDATION_CONFIG_PATH = f"{DATA_MANAGER_INTERNAL_FOLDER_PATH}/{VALIDATION_FOLDER}/{VALIDATION_CONFIG_FILE}"
    DEFAULT_FILE_ORCHESTRATION_CONFIG_PATH = f"{DATA_MANAGER_INTERNAL_FOLDER_PATH}/{FILE_ORCHESTRATION_FOLDER}/fileOrchestrationConfig.json"

    CLAIMS_CCLF_FILES_CONFIG_PATH = f"{DATA_MANAGER_INTERNAL_FOLDER_PATH}/{CLAIMS_FOLDER.lower()}/{CCLF_FOLDER.lower()}" 
    DEFAULT_DICOM_CONFIGS_PATH = f"{DATA_MANAGER_INTERNAL_FOLDER_PATH}/{MEDICAL_IMAGING_CONFIG_FOLDER}/{DICOM_FOLDER.lower()}"
    DEFAULT_CCLF_TO_FHIR_CONFIG_PATH = f"{DATA_MANAGER_INTERNAL_FOLDER_PATH}/{CLAIMS_FOLDER}/{CCLF_FOLDER}"
    DEFAULT_OMOP_SCRIPTS_PATH = f"{DATA_MANAGER_CONFIGURATION_FOLDER_ROOT}/{INTERNAL_FOLDER}/{OMOP_CONFIG_FOLDER}/{SCRIPTS_FOLDER}"
    DEFAULT_RMT_MAPPING_FOLDER = "mapping"
    DEFAULT_RMT_MAPPING_FOLDER_PATH = f"{DATA_MANAGER_CHECKPOINT_FOLDER_ROOT}/{DTT_CONFIG_FOLDER}/{DEFAULT_RMT_MAPPING_FOLDER}"
    DEFAULT_DTT_SECONDARY_LAKE_PATH = f"{DATA_MANAGER_CHECKPOINT_FOLDER_ROOT}/{DTT_CONFIG_FOLDER}/{DTT_STATE_DB}"
    DEFAULT_DTT_FILE_PATH = f"{DATA_MANAGER_CHECKPOINT_FOLDER_ROOT}/{DTT_CONFIG_FOLDER}"
    DEFAULT_DMF_CONFIG_PATH = f"{DATA_MANAGER_CHECKPOINT_FOLDER_ROOT}/{DTT_CONFIG_FOLDER}/{DMF_CONFIG_PATH}"
    DEFAULT_RMT_CONFIG_PATH = f"{DATA_MANAGER_CHECKPOINT_FOLDER_ROOT}/{DTT_CONFIG_FOLDER}/{RMT_CONFIG_PATH}"
    DEFAULT_IDM_DTT_SECONDARY_LAKE_PATH = f"{DATA_MANAGER_CHECKPOINT_FOLDER_ROOT}/{IDM_FOLDER}/{DTT_CONFIG_FOLDER}/{DTT_STATE_DB}"
    DEFAULT_IDM_DMF_CONFIG_PATH = f"{DATA_MANAGER_CHECKPOINT_FOLDER_ROOT}/{IDM_FOLDER}/{DTT_CONFIG_FOLDER}/{DMF_CONFIG_PATH}"
    DEFAULT_IDM_RMT_CONFIG_PATH = f"{DATA_MANAGER_CHECKPOINT_FOLDER_ROOT}/{IDM_FOLDER}/{DTT_CONFIG_FOLDER}/{RMT_CONFIG_PATH}"
    DEFAULT_IDM_ENV_CONFIG_PATH = f"{DATA_MANAGER_CHECKPOINT_FOLDER_ROOT}/{IDM_FOLDER}/{DTT_CONFIG_FOLDER}/{ENV_CONFIG_PATH}"
    DEFAULT_IDM_RMT_REFERENCE_DATA_FOLDER = f"{DATA_MANAGER_CONFIGURATION_FOLDER_ROOT}/{INTERNAL_FOLDER}/{IDM_FOLDER}/{IDM_RMT_REFERENCE_TABLES_FOLDER}"
    DEFAULT_IDM_RMT_REFERENCE_MAPPING_FOLDER = f"{DEFAULT_IDM_RMT_REFERENCE_DATA_FOLDER}/{IDM_RMT_REFERENCE_TABLES_MAPPING_FOLDER}/{IDM_RMT_REFERENCE_TABLES_DATA_HEALTHCARE_FOLDER}/{IDM_RMT_REFERENCE_TABLES_DOMAIN_FOLDER}"
    DEFAULT_SDOH_DTT_SECONDARY_LAKE_PATH = f"{DATA_MANAGER_CHECKPOINT_FOLDER_ROOT}/{SDOH_FOLDER}/{DTT_CONFIG_FOLDER}/{DTT_STATE_DB}"
    DEFAULT_SDOH_DMF_CONFIG_PATH = f"{DATA_MANAGER_CHECKPOINT_FOLDER_ROOT}/{SDOH_FOLDER}/{DTT_CONFIG_FOLDER}/{DMF_CONFIG_PATH}"
    DEFAULT_SDOH_RMT_CONFIG_PATH = f"{DATA_MANAGER_CHECKPOINT_FOLDER_ROOT}/{SDOH_FOLDER}/{DTT_CONFIG_FOLDER}/{RMT_CONFIG_PATH}"
    DEFAULT_SDOH_ENV_CONFIG_PATH = f"{DATA_MANAGER_CHECKPOINT_FOLDER_ROOT}/{SDOH_FOLDER}/{DTT_CONFIG_FOLDER}/{ENV_CONFIG_PATH}"
    DEFAULT_SDOH_RMT_REFERENCE_DATA_FOLDER = f"{DATA_MANAGER_CONFIGURATION_FOLDER_ROOT}/{INTERNAL_FOLDER}/{SDOH_FOLDER}/{IDM_RMT_REFERENCE_TABLES_FOLDER}"
    DEFAULT_SDOH_DMF_ADAPTER_CONFIG_PATH = f"{DATA_MANAGER_CHECKPOINT_FOLDER_ROOT}/{SDOH_FOLDER}/{DTT_CONFIG_FOLDER}/{SDOH_DMF_ADAPTER_FILE}"

    STREAM_ORCHESTRATOR_SLEEP_IN_SECONDS = 10

    # OMOP VOCAB SCHEMA
    OMOP_VOCAB_SCHEMA = {
        "CONCEPT": StructType(
            [
                StructField("concept_id", IntegerType()),
                StructField("concept_name", StringType()),
                StructField("domain_id", StringType()),
                StructField("vocabulary_id", StringType()),
                StructField("concept_class_id", StringType()),
                StructField("standard_concept", StringType()),
                StructField("concept_code", StringType()),
                StructField("valid_start_date", DateType()),
                StructField("valid_end_date", DateType()),
                StructField("invalid_reason", StringType()),
            ]
        ),
        "CONCEPT_RELATIONSHIP": StructType(
            [
                StructField("concept_id_1", IntegerType()),
                StructField("concept_id_2", IntegerType()),
                StructField("relationship_id", StringType()),
                StructField("valid_start_date", DateType()),
                StructField("valid_end_date", DateType()),
                StructField("invalid_reason", StringType()),
            ]
        ),
        "VOCABULARY": StructType(
            [
                StructField("vocabulary_id", StringType()),
                StructField("vocabulary_name", StringType()),
                StructField("vocabulary_reference", StringType()),
                StructField("vocabulary_version", StringType()),
                StructField("vocabulary_concept_id", IntegerType()),
            ]
        ),
        "CONCEPT_ANCESTOR": StructType(
            [
                StructField("ancestor_concept_id", IntegerType()),
                StructField("descendant_concept_id", IntegerType()),
                StructField("min_levels_of_separation", IntegerType()),
                StructField("max_levels_of_separation", IntegerType()),
            ]
        ),
        "CONCEPT_CLASS": StructType(
            [
                StructField("concept_class_id", StringType()),
                StructField("concept_class_name", StringType()),
                StructField("concept_class_concept_id", IntegerType()),
            ]
        ),
        "CONCEPT_SYNONYM": StructType(
            [
                StructField("concept_id", IntegerType()),
                StructField("concept_synonym_name", StringType()),
                StructField("language_concept_id", IntegerType()),
            ]
        ),
        "FHIR_SYSTEM_TO_OMOP_VOCAB_MAPPING": StructType(
            [
                StructField("fhir_uri", StringType()),
                StructField("vocabulary_id", StringType())
            ]
        )
    }

    CHECKPOINT_LOCATION_OPTION_NAME = "checkpointLocation"
    SILVER_CONFIG_RESOURCES_KEY: str = "resources"
    SILVER_CONFIG_NAME_KEY: str = "name"

    # public UDF function names
    PARSE_EXTENSION_UDF = "parse_extension"

    # Claims_Cms_Cclf
    CLAIMS_CMSCCLF_LANDINGZONE_TO_DELTATABLE: str = "ClaimsCmsCclfLandingZoneToDeltaTable"

    # Library telemetry usage activity name
    BRONZE_INGESTION_ACTIVITY_NAME = "raw-bronze-ingestion"
    SILVER_INGESTION_ACTIVITY_NAME = "bronze-silver-ingestion"
    OMOP_INGESTION_ACTIVITY_NAME = "silver-omop-ingestion"
    DTT_GENERIC_INGESTION_ACTIVITY_NAME = "dtt-generic-ingestion"
    FHIR_EXPORT_ACTIVITY_NAME = "fhir-export"
    OMOP_DRUG_ERA_GENERATOR_ACTIVITY_NAME = "omop-drug-era-table-generator"
    OMOP_VOCAB_INGESTION_ACTIVITY_NAME = "omop-vocabulary-ingestion"
    IMAGING_RAW_DATA_MOVEMENT_ACTIVITY_NAME = "imaging-raw-data-movement"
    IMAGING_METADATA_EXTRACTION_ACTIVITY_NAME = "imaging-metadata-extraction"
    IMAGING_PATCH_FILE_INGESTION_ACTIVITY_NAME = "imaging-patch-file-ingestion"
    SILVER_CUSTOM_INGESTION_ACTIVITY_NAME = "bronze-silver-custom-table-ingestion"
    IMAGING_FHIR_NDJSON_CONVERSION_ACTIVITY_NAME = "imaging-fhir-ndjson-conversion"
    IMAGING_METASTORE_PROCESSING_ACTIVITY_NAME = "imaging-metastore-processing"
    SDOH_BRONZE_INGESTION_ACTIVITY_NAME = "sdoh-raw-bronze-ingestion"
    DTT_WORKFLOW_ACTIVITY_NAME = "dtt-workflow"
    PATIENT_OUTREACH_SHORTCUTS_CREATION_ACTIVITY_NAME = "patientoutreach-shortcuts-creation"
    PATIENT_OUTREACH_GOLD_INGESTION_ACTIVITY_NAME = "patientoutreach-gold-ingestion"
    PATIENT_OUTREACH_SILVER_INGESTION_ACTIVITY_NAME = "patientoutreach-bronze-silver-ingestion"
    SDOH_SILVER_INGESTION_ACTIVITY_NAME = "sdoh-bronze-silver-ingestion"
    CMS_CCLF_FILES_DELTA_TABLES_INGESTION_ACTIVITY_NAME = "cms-cclf-delta-tables-raw-bronze-ingestion"
    CLAIMS_DELTA_TABLES_INGESTION_ACTIVITY_NAME = "claims-delta-tables-raw-bronze-ingestion"


    CMS_CCLF_FILES_BRONZE_INGESTION_ACTIVITY_NAME ="cms-cclf-raw-bronze-ingestion"
    CLAIMS_FILES_BRONZE_INGESTION_ACTIVITY_NAME ="claims-raw-bronze-ingestion"

    CM_ANALYTICS_GOLD_INGESTION_ACTIVITY_NAME = "cm-analytics-gold-ingestion"
    CI_SILVER_INGESTION_ACTIVITY_NAME = "ci-silver-ingestion"
    
    OPENAI_ENRICHMENT_ACTITVITY_NAME = "openai-enrichment-data"
     
    # Kusto Python Logs
    HDS_KUSTO_CUSTOM_DIMENSIONS = ["RunId", "PipelineRunId"]
    HDS_KUSTO_TABLE_NAME = "HealthcareDataSolutionsLogs"

    # Constants used for setting mounting timeouts
    MOUNT_FILE_CACHE_TIMEOUT = 100000
    MOUNT_TIMEOUT = 5000

    # Constants for Mounting Locations
    CLINICAL_FHIR_NDJSON_SOURCE_MOUNT_LOCATION = "/Clinical/FHIR-NDJSON"
    VALIDATION_FAILED_FILES_SOURCE_MOUNT_LOCATION = "/Validation_Failed/Source"
    VALIDATION_FAILED_FILES_TARGET_MOUNT_LOCATION = "/Validation_Failed/Target"
    # Parameter Persistence
    # Foundation Config Keys
    KEYVAULT_NAME_KEY = "keyvault_name"
    ADMIN_LAKEHOUSE_ID_KEY = "administration_lakehouse_id"
    BRONZE_LAKEHOUSE_ID_KEY = "bronze_lakehouse_id"
    SILVER_LAKEHOUSE_ID_KEY = "silver_lakehouse_id"
    OMOP_LAKEHOUSE_ID_KEY = "omop_lakehouse_id"
    PATIENT_OUTREACH_LAKEHOUSE_ID_KEY = "patient_outreach_lakehouse_id"
    CUSTOMER_INSIGHTS_LAKEHOUSE_ID_KEY = "customer_insights_lakehouse_id"
    CM_ANALYTICS_LAKEHOUSE_ID_KEY = "care_management_analytics_lakehouse_id"
    DATA_VALIDATION_CONFIG_PATH_KEY = "data_validation_config_path"
    FILE_MOVEMENT_CONFIG_PATH_KEY = "movement_config_path"
    ENABLE_HDS_LOGS_KEY = "enable_hds_logs"
    RUN_ID_KEY = "run_id"
    
    # DTT generic service config values
    DTT_SOURCE_LAKEHOUSE_ID_KEY = "dtt_source_lakehouse_id" 
    DTT_TARGET_LAKEHOUSE_ID_KEY = "dtt_target_lakehouse_id"
    DTT_SERVICE_CONFIG_PATH_KEY = "dtt_service_config_path"
    DTT_GENERIC_INGESTION_ACTIVITY_NOTEBOOK = "dtt_generic_ingestion_notebook"
    
    PIPELINE_RUN_ID_KEY= "pipeline_runId"
    PIPELINE_NAME_KEY= "pipeline_name"
    ENABLE_SUMMARY_METRICS_KEY = "enable_summary_metrics"
    METRICS_POLLING_INTERVAL_IN_MIN_KEY = "metrics_polling_interval"
    EXECUTION_SUMMARY_TABLE_PATH_KEY = "execution_summary_table_path"    
    
    #common constants for fhir convertor module
    FHIR_NDJSON_DATE_FORMAT = "%Y-%m-%dT%H.%M.%S.%fZ"
    FHIR_NDJSON_FILE_EXT = ".ndjson"
    FHIR_EXTENDED_ELEMENTS = ["identifier", "contained", "extension"]

    # Activity Config Keys
    # Shared
    MAX_BYTES_PER_TRIGGER_KEY = "max_bytes_per_trigger"
    MAX_FILES_PER_TRIGGER_KEY = "max_files_per_trigger"
    MAX_STRUCTURED_STREAMING_QUERIES_KEY = "max_structured_streaming_queries"
    OPTIMIZED_WRITE_BIN_SIZE_KEY = "optimize_write_bin_size"
    SHUFFLE_PARTITIONS_KEY = "shuffle_partitions"
    MAX_PARTITION_BYTES_KEY = "max_partition_bytes"
    PARQUET_DATE_REBASE_MODE_IN_WRITE_KEY = "parquet_date_rebase_mode_in_write"
    PARQUET_DATETIME_REBASE_MODE_IN_WRITE_KEY = "parquet_datetime_rebase_mode_in_write"
    SOURCE_TABLES_PATH_KEY = "source_tables_path"
    TARGET_TABLES_PATH_KEY = "target_tables_path"
    CHECKPOINT_PATH_KEY = "checkpoint_path"
    SCHEMA_DIR_PATH_KEY = "schema_dir_path"
    # Raw Process Movement
    MODALITY_KEY = "modality"
    MODALITY_FORMAT_KEY = "modality_format"
    MAX_ARCHIVE_FILE_SIZE_IN_GB_KEY = "max_archive_file_size_in_gb"
    MAX_THREAD_TO_EXTRACT_ARCHIVE_FILE_KEY = "max_thread_to_extract_archive_file"
    MAX_THREAD_TO_MOVE_FILE_KEY = "max_thread_to_move_file"
    ROOT_FILE_INGESTION_PATH_KEY = "root_file_ingestion_path"
    ROOT_TARGET_FILE_PATH_KEY = "root_target_file_path"
    # Clinical Bronze Ingestion
    SOURCE_PATH_KEY = "source_path"
    SOURCE_PATH_PATTERN_KEY = "source_path_pattern"
    DELTA_TABLE_PATH_KEY = "delta_table_path"
    # Clinical Bronze Ingestion
    MOVE_FAILED_FILES_ENABLED_KEY = "move_failed_files_enabled"
    COMPRESSION_ENABLED_KEY = "compression_enabled"
    TARGET_TABLE_NAME_KEY = "target_table_name"
    FILE_EXTENSION_KEY = "file_extension"
    VALIDATION_CONFIG_KEY = "validation_config_key"
    DELTA_LOG_RETENTION_DURATION_KEY = "delta_log_retention_duration"
    DELTA_DELETED_FILE_RETENTION_DURATION_KEY = "delta_deleted_file_retention_duration"
    BUSINESS_EVENTS_TABLE_PATH_KEY = "business_events_table_path"
    BUSINESS_EVENTS_SCHEMA_DIR_PATH_KEY = "business_events_schema_dir_path"
    # Clinical Silver Ingestion
    CONFIG_PATH_KEY = "config_path"
    SOURCE_TABLE_NAME_KEY = "source_table_name"
    # Clinical Gold Ingestion
    OMOP_CONFIG_PATH_KEY = "omop_config_path"
    OMOP_SCRIPTS_PATH_KEY = "omop_scripts_path"
    VOCAB_LAKEHOUSE_NAME_KEY = "vocab_lakehouse_name"
    VOCAB_PATH_KEY = "vocab_path"
    VOCAB_CHECKPOINT_PATH_KEY = "vocab_checkpoint_path"
    DTT_SECONDARY_LAKE_PATH_KEY = "dtt_secondary_lake_path"
    DMF_CONFIG_PATH_KEY = "dmf_config_path"
    RMT_CONFIG_PATH_KEY = "rmt_config_path"
    DTT_ROOT_DIR_PATH_KEY = "dtt_root_dir_path"
    DTT_RMT_MAPPING_INPUT_DIR_PATH_KEY = "dtt_rmt_mapping_input_dir_path"
    DTT_RMT_REFERENCE_TABLES_DIR_PATH_KEY = "dtt_rmt_reference_tables_dir_path"
    RMT_MAPPING_INPUT_DIR_PATH_KEY = "rmt_mapping_input_dir_path"
       # Fhir Export
    MAX_POLLING_DAYS_KEY = "max_polling_days"
    # POA Bronze Silver Ingestion
    CI_PROFILE_ID_KEY = "ci_profile_id"
    CI_DEFAULT_PROFILE_ID = "msdynci_patientnewid"
    IDM_CONFIG_PATH_KEY = "idm_config_path"
    # POA Gold Ingestion
    POAGOLD_CONFIG_PATH_KEY = "poagold_config_path"
    DAYS_FROM_JOURNEY_KEY = "days_from_journey"
    # Claims CCLF Bronze Ingestion
    CONFIG_FILE_PATH_KEY = "cclf_to_fhir_config_path"
    AVRO_SCHEMA_PATH_KEY = "avro_schema_path"
    FHIR_NDJSON_FILES_ROOT_PATH_KEY = "fhir_ndjson_files_root_path"
    FHIR_NAMESPACE_KEY = "fhir_namespace"
    DELTA_TABLE_PATH_KEY = "delta_table_path"
    MAX_RECORDS_PER_NDJSON_KEY = "max_records_per_ndjson"
    # Claims CCLF Delta Tables Ingestion
    CMS_CCLF_FILES_DROP_PATH_KEY = "cms_cclf_files_drop_path"
    CCLF_FILES_CONFIG_PATH_KEY = "cclf_files_config_path"
    CLAIMS_CHECKPOINT_PATH_KEY = "claims_checkpoint_path"
    CLAIMS_ROW_VALUE = 'value'
    # Imaging Bronze Ingestion
    IMAGING_TABLE_SCHEMA_PATH_KEY = "bronze_imaging_table_schema_path"
    IMAGING_DELTA_TABLE_PATH_KEY = "bronze_imaging_delta_table_path"
    MOVE_FAILED_FILES_KEY = "move_failed_files"
    NUM_RETRIES_KEY = "num_retries"
    INGESTION_PATTERN_KEY = "ingestion_pattern"
    EXTERNAL_SOURCE_PATH_KEY = "external_source_path"
    PROCESS_SOURCE_PATH_KEY = "process_source_path"
    INVENTORY_SOURCE_PATH_KEY = "inventory_source_path"
    INVENTORY_FOLDER_NAME_KEY = "inventory_folder_name"
    AZURE_BLOB_STORAGE_INVENTORY_KEY = "azure_blob_storage_inventory"
    IMAGING_PATCH_FILE_BUSINESS_EVENTS_TABLE_LOGGING_KEY = "business_event_table_logging_enabled"
    DICOM_PATCH_PROCESS_TYPE_KEY = "process_type"
    NAMESPACE_KEY = "namespace"
    ROWS_PER_PARTITION_KEY = "rows_per_partition"
    DICOM_EXTRACT_LIB_PARAMS_KEY = "dicom_extract_lib_params"
    # Imaging FHIR Conversion
    BASE_CHECKPOINT_PATH_KEY = "base_checkpoint_path"
    DICOM_TO_FHIR_CONFIG_PATH_KEY = "dicom_to_fhir_config_path"
    IMAGING_METASTORE_TABLE_PATH_KEY = "metastore_table_path"
    AVRO_SCHEMA_PATH_KEY = "avro_schema_path"
    FHIR_NDJSON_FILES_ROOT_PATH_KEY = "fhir_ndjson_files_root_path"
    MAX_RECORDS_PER_NDJSON_KEY = "max_records_per_ndjson"
    # CMA Gold Ingestion
    CMA_GOLD_CONFIG_PATH_KEY = "cma_gold_config_path"
    # SDOH Bronze Ingestion
    SDOH_PROCESS_FOLDER_PATH_KEY = "sdoh_process_folder_path"
    # SDOH Silver Ingestion
    SDOH_CONFIG_PATH_KEY = "sdoh_config_path"
    # NLP Silver Ingestion
    ENABLE_TEXT_ANALYTICS_LOGS_KEY = "enable_text_analytics_logs"
    TABLES_PATH_KEY = "tables_path"

    
    # AI Enrichment
    DEFAULT_AI_ENRICHMENT_CONFIG_PATH =f"{DATA_MANAGER_INTERNAL_FOLDER_PATH}/ai_enrichment"
    DEFAULT_AI_ENRICHMENT_RESOURCES_PATH = f"{DEFAULT_AI_ENRICHMENT_CONFIG_PATH}/output_types"
    AI_ENRICHMENT_RESOURCE_SCHEMA_PATH_KEY = "ai_enrichment_resource_schema_path"
    AI_ENRICHMENT_EXTRACT_FHIR_RESOURCES_FROM_ENRICHMENT_OBJECT_KEY = "extract_fhir_resources_from_object_enrichments"

    # DAX shared
    DAX_CONFIG_PATH_KEY = "dax_config_path"
    # DAX Bronze Ingestion
    DAX_LANDING_ZONE_LAKEHOUSE_ID_KEY = "dax_landing_zone_lakehouse_id"
    DAX_TARGET_TABLE_NAME_KEY = "dax_target_table_name"
    # DAX Silver Ingestion
    DAX_SOURCE_TABLE_NAME_KEY = "dax_source_table_name"
    DAX_RESOURCE_SCHEMA_PATH_KEY = "dax_resource_schema_path"