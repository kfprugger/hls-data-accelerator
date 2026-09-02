# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
"""
Module with a class containing constants used through out the package
"""

class SdohConstants:
    """
    This class contains constants used through out sdoh module
    """    
    NON_DATA_CSV_LIST = ["Layout.csv", "DataSetMetadata.csv", "LocationConfiguration.csv"]
    NON_DATA_SHEET_LIST = ["Layout", "DataSetMetadata", "LocationConfiguration"]
    LAYOUT_COLUMN_LIST = ["Category", "SubCategory", "SocialDeterminantDescription", "SocialDeterminantName", "Units", "HarmonizationKey"]
    LAYOUT_MANDATORY_COLUMN_LIST = ["SocialDeterminantDescription", "SocialDeterminantName"]
    METADATA_COLUMN_LIST = ["DatasetName", "PublisherName", "PublishedDate", "ValidUntil"]  
    SDOH_TARGET_TABLES_LIST = ['SocialDeterminant', 'SocialDeterminantDataSetMetadata', 'SocialDeterminantCategory', 'SocialDeterminantSubCategory', 'UnitOfMeasure']
    LOC_CONFIG_COLUMN_NAME="ColumnName"
    LOC_CONFIG_STANDARD_COLUMN_NAME="StandardColumnName"
    LOC_CONFIG_ASSOCIATED_WITH_SDOH_VALUE="AssociatedWithSDOHValue"
    COLUMN_DATASET_METADATA_ID = "DataSetMetadataId"
    COLUMN_LOC_CONFIG = "LocationConfiguration"
    SHEETNAME_METADATA = "DataSetMetadata"
    SHEETNAME_LAYOUT = "Layout"
    SHEETNAME_LOCCONFIG = "LocationConfiguration"
    COLUMN_FIPS = "FIPS"
    COLUMN_STATE_FIPS = "StateFIPS"
    COLUMN_LAYOUT_ID = "LayoutID"
    FORMAT_DELTA = "delta"
    MODE_OVERWRITE = "overwrite"
    MODE_APPEND = "append"
    DOT = "."
    UNDERSCORE = "_"
    FILETYPE_CSV = ".csv"
    FILETYPE_XLSX = ".xlsx"
    FILETYPE_XLS = ".xls"
    SD_PREFIX = "Sdoh"
    COMMA_SEPARATOR = ","
    NOW = "now"
    FIVE = 5
    TWO = 2
    Zero = 0
    PUBLISHED_DATE = "PublishedDate"
    VALIDITY_DATE = "ValidUntil"
    FOLDER_PATH = "FolderPath"
    DEFAULT_SDOH_BRONZE_INGESTION_RETRY_DELAY=5
    LOCATION_COLUMN_NAME = "ColumnName"
    AVRO_SCHEMA_FILE_EXT = ".avsc"
    TABLE_SOCIAL_DETERMINANT = "SocialDeterminant"
    