# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
"""
Module with a class containing validation steps for bronze ingestion
"""
from microsoft.fabric.hls.hds.sdoh.bronze_ingestion.constants import SdohConstants
from microsoft.fabric.hls.hds.utils.utils import Utils as PlatformCommonUtil
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants
import pandas

class Validator:
    def validate_layout_df(self, layout_df) -> bool:
        """
        Iterate through the list of layout table mandatory columns and check if they are present in the layout dataframe
         Args:
        - layout_df -  Dataset layout dataframe to be validated
        """
        if layout_df is None:
            return False
        column_names = layout_df.columns.tolist()    
        column_names = [col_name.strip().lower() for col_name in column_names]
        
        mandatory_columns = {col.lower() for col in SdohConstants.LAYOUT_MANDATORY_COLUMN_LIST} 
        allowed_columns = {col.lower() for col in SdohConstants.LAYOUT_COLUMN_LIST} 
    
        return mandatory_columns.issubset(column_names) and set(column_names).issubset(allowed_columns)

    def validate_metadata_df(self, metadata_df) -> bool:
        """
        Iterate through the list of datasetmetadata table columns and check if they are present in the metadata dataframe
        Args:
        - metadata_df -  Dataset metadata dataframe to be validated
        """
        if metadata_df is None:
            return False
        column_names = metadata_df.columns.tolist()
        column_names = [col_name.strip().lower() for col_name in column_names]  
        
        expected_columns = {col.lower() for col in SdohConstants.METADATA_COLUMN_LIST} 
        
        return set(column_names) == expected_columns
    
    def validate_loc_conf_df(self, loc_config_df) -> bool:
        """
        Iterate through the location configuration provided and returns whether the it is valid or not
        Args:
        - loc_config_df -  Location configuration dataframe to be validated
        A Valid location configuration looks like this:
        |-----------------------------------------------------------|
        | ColumnName | StandardColumnName | AssociatedWithSDOHValue |
        |------------|--------------------|-------------------------|
        | STATE_NAME | STATE              | false                   |
        | CNTY       | COUNTY             | true                    |
        |-----------------------------------------------------------|
        """
        if loc_config_df is None:
            return False
        column_names = loc_config_df.columns.tolist()
        column_names = [col_name.strip() for col_name in column_names]
        LOC_CONFIG_COLUMN_LIST=[SdohConstants.LOC_CONFIG_COLUMN_NAME,SdohConstants.LOC_CONFIG_STANDARD_COLUMN_NAME,SdohConstants.LOC_CONFIG_ASSOCIATED_WITH_SDOH_VALUE]
        return (set(column_names) == set(LOC_CONFIG_COLUMN_LIST))  and (pandas.isnull(loc_config_df).sum().sum() == 0)
    

    def validate_excel_dataset(self, excel_df, file_path) -> str:
        """
        Validates excel dataset for the required sheets and columns
        Args:
        - excel_df - Dataframe for the excel dataset
        - file_path - Path of the excel dataset
        Returns:
        - str: Error message if any
        """
        if not (file_path.endswith(SdohConstants.FILETYPE_XLSX) or file_path.endswith(SdohConstants.FILETYPE_XLS)):
            return f"{LoggingConstants.INVALID_EXCEL_FILE_FORMAT.format(file_path=file_path)}"
        if SdohConstants.SHEETNAME_METADATA not in excel_df.sheet_names:
            return f"{LoggingConstants.INVALID_DATASET_MISSING_METADATA.format(file_path=file_path)}"
        if SdohConstants.SHEETNAME_LAYOUT not in excel_df.sheet_names:
            return f"{LoggingConstants.INVALID_DATASET_MISSING_LAYOUT.format(file_path=file_path)}"
        if SdohConstants.SHEETNAME_LOCCONFIG not in excel_df.sheet_names:
            return f"{LoggingConstants.INVALID_DATASET_MISSING_LOCATION_CONFIG.format(file_path=file_path)}"
        if not self.validate_metadata_df(excel_df.parse(sheet_name=SdohConstants.SHEETNAME_METADATA)):
            return f"{LoggingConstants.INVALID_METADATA_INFORMATION.format(file_path=file_path)}"
        if not self.validate_layout_df(excel_df.parse(sheet_name=SdohConstants.SHEETNAME_LAYOUT)):
            return f"{LoggingConstants.INVALID_LAYOUT_INFORMATION.format(file_path=file_path)}"
        if not self.validate_loc_conf_df(excel_df.parse(sheet_name=SdohConstants.SHEETNAME_LOCCONFIG)):
            return f"{LoggingConstants.INVALID_LOC_CONFIG_INFORMATION.format(file_path=file_path)}"
        if not len(excel_df.sheet_names) > 3:
            return f"{LoggingConstants.INVALID_DATASET_MISSING_DATA.format(file_path=file_path)}"
        return None

    def validate_csv_dataset(self, folder_path, timestamp, mssparkutils_client) -> str:
        """
        Validate csv file
        Args:
        - folder_path - Folder path for the dataset
        - timestamp - Timestamp of the dataset
        Returns:
        - str: Error message if any
        """
        if not self.file_exists_with_partial_name(folder_path, mssparkutils_client,f"{SdohConstants.SHEETNAME_METADATA}{SdohConstants.FILETYPE_CSV}"):
            return f"{LoggingConstants.INVALID_DATASET_MISSING_METADATA.format(file_path=folder_path)}"
        if not self.file_exists_with_partial_name(folder_path, mssparkutils_client,f"{SdohConstants.SHEETNAME_LAYOUT}{SdohConstants.FILETYPE_CSV}"):
            return f"{LoggingConstants.INVALID_DATASET_MISSING_LAYOUT.format(file_path=folder_path)}"
        if not self.file_exists_with_partial_name(folder_path, mssparkutils_client,f"{SdohConstants.SHEETNAME_LOCCONFIG}{SdohConstants.FILETYPE_CSV}"):
            return f"{LoggingConstants.INVALID_DATASET_MISSING_LOCATION_CONFIG.format(file_path=folder_path)}"
        files = PlatformCommonUtil.list_files(folder_path, mssparkutils_client)
        if not len([file.name for file in files if file.name.endswith(SdohConstants.FILETYPE_CSV) and file.name.split('_', 1)[1] not in SdohConstants.NON_DATA_CSV_LIST]) > 0:
            return f"{LoggingConstants.INVALID_DATASET_MISSING_DATA.format(file_path=folder_path)}"
        return None
    
    def validate_data(self, df, loc_columns, file_path) -> str:
        """
        Check if the data has atleast two columns
        Args:
        - df - Dataframe to be validated
        - loc_columns - List of location columns
        - file_path - Path of the data sheet
        Returns:
        - str: Error message if any
        """
        if len(df.columns) < SdohConstants.TWO:
            return f"{LoggingConstants.INVALID_DATAFILE_ONE_COLUMN.format(file_path=file_path)}"
        haslocation = False
        hasData = False
        for column in df.columns.tolist():
            if column in loc_columns:
                haslocation = True
            else:
                hasData = True
            if hasData and haslocation:
                return None
        if hasData:
            return f"{LoggingConstants.INVALID_DATAFILE_MISSING_LOCATION_COLUMN.format(file_path=file_path)}"
        else:
            return f"{LoggingConstants.INVALID_DATAFILE_MISSING_DATA_COLUMN.format(file_path=file_path)}"
        
    def file_exists_with_partial_name(self, folder_url: str,mssparkutils_client, partial_name: str) -> bool:
        """
        Check if a directory contains a file with a partial name match.

        Args:
        - folder_url (Union[Url, str]): The directory to search in.
        - mssparkutils_client: The Spark utils client for file operations.
        - partial_name (str): The partial name of the file to search for.

        Returns:
        - bool: True if a file with the partial name exists, False otherwise.
        """
        # List all files in the directory
        files = PlatformCommonUtil.list_files(folder_url,mssparkutils_client)
        
        # Check if any file contains the partial name
        for file in files:
            if partial_name in file.name:
                return True
        return False