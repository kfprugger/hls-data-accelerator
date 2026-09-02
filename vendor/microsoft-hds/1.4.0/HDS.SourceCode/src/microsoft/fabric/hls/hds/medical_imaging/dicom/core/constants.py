# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
"""
Module with a class containing constants used through out the package
"""
from pyspark.sql.types import *
from enum import Enum
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC

class ImagingStudyConstants:
    """
    This class contains constants used through out medical_imaging module
    """
    
    class IngestionPattern(Enum):
        INGEST = 0
        BYOS = 1
        INVENTORY = 2
        
    class ProcessType(Enum):
        DICOM = "dicom"
        PATCH = "patch"
    
    DEFAULT_INVENTORY_FOLDER_NAME = "InventoryFiles"
     
    ME_MAX_FILES_PER_TRIGGER = 100000
    ME_MAX_BYTES_PER_TRIGGER = 1000000000 #1GB
    ME_DEFAULT_ROWS_PER_PARTITION = 250
    
    #Azure blob storage inventory constants
    AZ_INVEN_NAME_FIELD = "Name"
    AZ_INVEN_LAST_MODIFIED_FIELD = "Last-Modified"
    AZ_INVEN_IS_FOLDER_FIELD = "hdi_isfolder"
    
    #constants used for setting mounting timeouts
    MOUNT_FILE_CACHE_TIMEOUT = 100000
    MOUNT_TIMEOUT = 5000
    META_EXTRACT_MOUNT_LOCATION = f"/{GC.MEDICAL_IMAGING_FOLDER}/{GC.DICOM_FOLDER}/metadata_extraction"
    PATCH_FILE_MOUNT_LOCATION = f"/{GC.MEDICAL_IMAGING_FOLDER}/{GC.IMAGING_OPERATIONS_FOLDER}/patch_file_ingestion"
    
    STATE_STARTED = 'started'
    STATE_COMPLETED = 'completed'
    
    METADATA_EXTRACT_CHECKPOINT_FOLDER = "dicom_metadata_extraction"
    DCM_FILE_DROP_FOLDER = "Ingest"
    DCM_INGEST_MOUNT_POINT_NAME = "/imaging/DICOM"
    PATCH_FILE_INGESTION_CHECKPOINT_FOLDER = "patch_file_ingestion"
    
    METADATA_EXTRACTION_PROCESS_NAME = "Metadata Extraction"
    PATCH_FILE_PROCESS_NAME = "Patch File Ingestion"
    SILVER_METASTORE_PROCESS_NAME = "Imaging Metastore Processing"
    ARCHIVE_EXTRACTION_PROCESS_NAME = "Archive Extraction"

    FAILED_FILES_FOLDER = "Failed"
    FAILED_NUM_RETRIES = 1
    PIXEL_DATA_FAILURE_ERROR = "PixelData"
    NON_RETRIABLE_ERRORS = [PIXEL_DATA_FAILURE_ERROR]
    
    METADATA_TABLE_NAME = "ImagingDicom"
    IMAGING_META_STORE = "ImagingMetastore"
    CALC_FIELD = "calc"
    FILE_PATH_COLUMN_NAME = "filePath"
    INVENTORY_FILE_PATH_COLUMN_NAME = "inventoryFilePath"
    TAGS_JSON_COLUMN_NAME = "metadata"
    TAGS_METADATA_STRING = "metadata_string"
    
    ID_COLUMN_NAME = "id"
    SOURCE_MODIFIED_COLUMN_NAME = "sourceModifiedAt"
    SOURCE_SYSTEM_COLUMN_NAME = "sourceSystem"
    
    ERROR_ATTR_NAME = "error"
    DCM_FILE_CONTENT_ATTR_NAME = "content"
    MODIFICATION_TIME_ATTR_NAME = "modificationTime"
    LENGTH_ATTR_NAME = "length"
    PATH_ATTR_NAME = "path"
    FAILED_TAGS_ATTR_NAME = "failedTags"
    EXTRACTED_METADATA_ATTR_NAME = "metadataExtracted"
    
    IGNORE_FIELDS = ['metadata','metadata_string','modalitiesinstudy_string','createddatetime']

    IMAGING_META_STORE_COLUMNS = ['studyInstanceUid','seriesInstanceUid','sopInstanceUid', 'sourceSystem', 'metadata','metadata_string','filePath','sourceModifiedAt','msftIsDeleted']
    IMAGING_META_STORE_UNIQUE_COLUMNS = ['studyInstanceUid','seriesInstanceUid','sopInstanceUid', 'msftSourceSystem']
    DEFAULT_DICOM_PATCH_PROCESS_TYPE = "dicom"
    SILVER_SOURCE_SYSTEM_COLUMN_NAME = "msftSourceSystem"    

    DEFAULT_TAGS_AS_COLUMN = ['StudyInstanceUID', 'SeriesInstanceUID', 'SOPInstanceUID']
    ME_TRANSFORMATION_COLUMNS = ['studyInstanceUID', 'seriesInstanceUID', 'sopInstanceUID', 'metadata']


    #constants used for dicom metadata to fhir ndjson conversion
    D2F_MAX_FILES_PER_TRIGGER = 10
    D2F_MAX_BYTES_PER_TRIGGER = 2000000000
    
    DICOM_TO_FHIR_CHECKPOINT_FOLDER = "dicom_to_fhir"
    AVRO_SCHEMA_FILE_EXT = ".avsc"
    DICOM_TO_FHIR_MAPPING_FILE_NAME = "metadata_fhir_mapping.json"
    DICOM_TABLES_SCHEMA_FILE_NAME = "table_schema.json"
    
    GROUP_BY_ELEMENTS = {
        'instance' : ['studyInstanceUid', 'seriesInstanceUid', 'sopInstanceUid', SOURCE_SYSTEM_COLUMN_NAME],
        'series': ['studyInstanceUid', 'seriesInstanceUid', SOURCE_SYSTEM_COLUMN_NAME],
        'ImagingStudy': ['studyInstanceUid', SOURCE_SYSTEM_COLUMN_NAME]
    }
    
    FHIR_IMAGING_STUDY_RES_NAME = "ImagingStudy"
    FHIR_SERIES_ELEMENT = "series"
    
    MAX_RECORDS_PER_NDJSON = 1000
    
    #business events related constants
    IMAGING_NOTEBOOK_ME = "imaging_dicom_extract_bronze_ingestion"
    IMAGING_PATCH_FILE_NOTEBOOK = "imaging_operations_patch_file_bronze_ingestion"
    IMAGING_NOTEBOOK_D2F = "imaging_dicom_fhir_conversion"
    SILVER_IMAGING_METASTORE_SERVICE = "silver_imaging_metastore_service"
    
    BE_EVENT_TYPE_ME_INIT_FAILED = "Class:MetadataExtractionOrchestrator. Method: __init__. Step: class inititatization failed."
    BE_EVENT_TYPE_FAILED_FILES_INFO_COLLECT = "Class:MetadataExtractionOrchestrator. Method: _process_dcm_files. Step: processing_failed_rows_collecting count of total, fail and success rows."
    BE_EVENT_TYPE_FAILED_FILES_NOT_MOVED = "Class:MetadataExtractionOrchestrator. Method: _process_dcm_files. Step: Unable to move failed files."    
    BE_EVENT_TYPE_FAILED_FILES = "Class:MetadataExtractionOrchestrator. Method: _process_dcm_files. Step: processing_failed_rows."
    BE_EVENT_TYPE_FAILED_FILES_NON_RETRIABLE_ERRORS = "Class:MetadataExtractionOrchestrator. Method: _process_dcm_files. Step: NON_RETRIABLE_ERRORS."
    
    BE_EVENT_TYPE_D2F_EXECUTE_NDJSON_GENERATION = "Class:MetadataToFhirConvertor. Method: execute_ndjson_generation. Step: call to generate ndjson file."

    BE_EVENT_TYPE_MS_UPSERT_FAILED = "Class:ImagingSilverMetaStoreCreator. Method:transform_data. Step:Upsert to silver ImagingMetastore table failed."
    
    #constants for extract_metadata parameters
    STOP_BEFORE_PIXELS_KEY = "stop_before_pixels"
    SUPPRESS_VALIDATION_TAGS_KEY = "suppress_validation_tags"
    DICOM_EXTRACT_LIB_PARAMS = "{'stop_before_pixels': False, 'suppress_validation_tags': False}"
    
    #patch file ingestion constants
    TAG_STRING = "tag_string"
    STUDY_INSTANCE_UID = "studyInstanceUid"
    SERIES_INSTANCE_UID = "seriesInstanceUid"
    SOP_INSTANCE_UID = "sopInstanceUid"
    OPERATION = "operation"
    DELETE_OPERATION = "soft-delete"
    PATCH_OPERATION = "patch"
    
    MODALITIES_IN_STUDY_STRING = "modalitiesInStudy_string"
    IMAGING_PATCH_META_STORE_COLUMNS = ['studyInstanceUid','seriesInstanceUid','sopInstanceUid', 'sourceSystem', 'metadata','sourceModifiedAt']   
    
    INCR_STUDY_INSTANCE_UID = "Incremental_studyInstanceUid"
    INCR_SERIES_INSTANCE_UID = "Incremental_seriesInstanceUid"
    INCR_SOP_INSTANCE_UID = "Incremental_sopInstanceUid"
    INCR_METADATA = "Incremental_metadata"
    INCR_SOURCE_MODIFIED = "Incremental_sourceModifiedAt"    

    METADATA_COLUMN_NAME = "metadata"
    METASTORE_DELETED_COLUMN_NAME = "msftIsDeleted"

    NDJSON_IGNORE_FIELDS = ['metadata','metadata_string','modalitiesinstudy_string','createddatetime','studyInstanceUid','seriesInstanceUid','sopInstanceUid']
                
    METADATA_SCHEMA = MapType(
    StringType(),
    StructType([
        StructField("vr", StringType(), True),
        StructField("Value", ArrayType(StringType()), True)
    ]))
    
    PATCH_FILE_SCHEMA = StructType([
        StructField("id", StringType(), True),
        StructField("meta", StructType([
            StructField("lastUpdated", StringType(), True)
        ]), True),
        StructField("resourceType", StringType(), True),
        StructField("identifier", ArrayType(StructType([
            StructField("system", StringType(), True),
            StructField("value", StringType(), True),
        ])), True),
        StructField("series", ArrayType(StructType([
            StructField("uid", StringType(), True),
            StructField("instance", ArrayType(StructType([  # Explicitly define instance as an ArrayType of StructType
                StructField("uid", StringType(), True)
            ]), True), True)
        ])), True),
        StructField("extension", ArrayType(StructType([
            StructField("url", StringType(), True),
            StructField("valueString", StringType(), True)
        ])), True)
    ])