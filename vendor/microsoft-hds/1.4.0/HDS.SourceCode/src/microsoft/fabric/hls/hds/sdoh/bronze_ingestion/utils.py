# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
"""
Module with a class containing utility methods for bronze ingestion
"""
import os
import re
import io
import pandas
from datetime import datetime
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.sdoh.bronze_ingestion.constants import SdohConstants
from microsoft.fabric.hls.hds.utils.utils import Utils as PlatformCommonUtil
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase
from pyspark.sql import DataFrame
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC

class SdohUtils:
    """
    This class contains utilities used through out sdoh module
    """
    def read_csv_stream(self, byte_object, filepath) -> pandas.DataFrame:
        """
        Process a CSV file from a byte object.

        Args:
        - byte_object : The byte object containing the CSV data.
        - filepath : The path of the file being processed.

        Returns:
        - pandas.DataFrame: The CSV data as a pandas DataFrame.
        """
        try:
            data = io.BytesIO(byte_object)
            csv_df = pandas.read_csv(data, dtype=str)
            return csv_df
        except Exception as ex:
            raise Exception(f"{LC.CSV_READ_FAILURE.format(file_path = filepath, error_message = str(ex))}")

    def prepare_location_configuration(self, loc_config_df: DataFrame) -> str:
        """
        Prepare location configuration
        Args:
        - loc_config_df - Location configuration dataframe.
        Example: Ideally location configuration input in a sheet looks like this:
        |------------------------------------------------------|
        | ColumnName | StandardColumnName | AssociatedWithSDOHValue |
        |------------|--------------------|-------------------------|
        | STATE_NAME | STATE              | false                   |
        | CNTY       | COUNTY             | true                    |
        |-----------------------------------------------------------|
        """
        return loc_config_df.to_json(orient='records')

    def get_directory(self, path: str) -> str:
        """
        Returns the directory of the given path.

        Args:
            path (str): The path for which to retrieve the directory.

        Returns:
            str: The directory of the given path.
        """
        return os.path.dirname(path)

    def check_filename(self, file_name):
        """
        Checks if the given file name starts with a six-digit number.

        Args:
            file_name (str): The name of the file to be checked.

        Returns:
            str: The prefix of the file name if it starts with a six-digit number, otherwise an empty string.
        """
        if re.search(r"^\d+\.\d+.*", file_name):
            file_name_prefix = file_name.split("_", 1)[0]
            return file_name_prefix
        else:
            return ""

    def get_locationColumns(self, loc_conf_df)->list:
        """
        Get location columns
        Args:
            loc_conf_df - Location configuration dataframe
        Returns:
            list: List of location column names
        """
        return loc_conf_df[SdohConstants.LOCATION_COLUMN_NAME].tolist()

    def _move_files_to_failed_folder(self, df_files: DataFrame, failed_folder: str, mssparkutils_client:MSSparkUtilsClientBase) -> None:
        """
        Moves the files from the process folder to the failed folder and removes the source folder once all the files are moved.

        Args:
            df_files (DataFrame): A DataFrame containing list of files to be moved.
            failed_folder (str): The path of the failed folder.
            mssparkutils_client (MSSparkUtilsClientBase): The client to use for interacting with the file system.
        """
        if df_files is not None and not df_files.isEmpty():
            for file in df_files.collect():
                # Get the source path
                source_path = self.get_directory(file.path)
                self._move_folder_to_failed_folder(source_path, failed_folder, mssparkutils_client)

    def _move_folder_to_failed_folder(self, source_path: str, failed_folder: str, mssparkutils_client:MSSparkUtilsClientBase) -> None:
        """
        Moves the files from the source folder to the failed folder and removes the source folder once all the files are moved.
        Args:
            source_path (str): The path of the source folder.
            failed_folder (str): The path of the failed folder.
            mssparkutils_client (MSSparkUtilsClientBase): The client to use for interacting with the file system.
        """
        #check path exists
        if PlatformCommonUtil.path_exists(source_path, mssparkutils_client):
            # Get the sub folders path
            sub_folder_path = self.extract_path_after_sdoh(source_path)
            # get all the files from the source folder.Remove prefix and then  move to target folder and remove the source folder once all the files moved to target
            unprocessed_files = PlatformCommonUtil.list_files(source_path, mssparkutils_client)
            for file in unprocessed_files:
                if not file.isDir:
                    # Get the base name of the file
                    base_name = os.path.basename(file.path)
                    
                    # Construct the new path
                    if not PlatformCommonUtil.path_exists(failed_folder, mssparkutils_client):
                        PlatformCommonUtil.create_folder(failed_folder,mssparkutils_client)
                    new_subdir = os.path.join(failed_folder, sub_folder_path)
                    if not PlatformCommonUtil.path_exists(new_subdir, mssparkutils_client):
                        PlatformCommonUtil.create_folder(new_subdir, mssparkutils_client)
                    new_path = os.path.join(new_subdir, base_name)
                    
                    # Move the file to the new path
                    PlatformCommonUtil.move_folders_files(file.path, new_path, mssparkutils_client)
            
            
    def extract_path_after_sdoh(self, file_path: str) -> str:
        """
        Extracts the path after 'SDOH' from the given file path.

        Args:
        - file_path (str): The full file path.

        Returns:
        - str: The extracted sub-path after 'SDOH'.
        """
        # Regular expression to find a 4-digit number followed by two 2-digit numbers
        pattern = re.compile(r'(\d{4})/(\d{2})/(\d{2})')
        
        # Search for the pattern in the file_path
        match = pattern.search(file_path)
        if not match:
            raise Exception(f"{LC.SDOH_INCORRECT_SOURCE_PATH_ERR_MSG}")
        
        # Get the matched strings
        year = match.group(1)
        month = match.group(2)
        
        # Split the URL into components
        components = file_path.split('/')
        
        # Get the start indices of the matched strings
        year_index = components.index(year)
        month_index = components.index(month)
        
        # Check if the current month is one level down from the current year
        if month_index == year_index + 1:
            # Get the folder structure two levels up from the current year
            if year_index >= 2: 
                two_levels_up = '/'.join(components[year_index - 2:year_index + 1])
                # Get everything after the year index
                after_year = '/'.join(components[year_index + 1:])
                
                sub_path = f"{two_levels_up}/{after_year}"
        
        return sub_path
    
    def to_pascal_case(self,name: str) -> str:
        """
        Convert a given string to PascalCase.

        This function splits the input string by changes from lowercase to uppercase letters and digits,
        capitalizes the first letter of each component, and joins them together to form a PascalCase string.

        Args:
            name (str): The input string to be converted.

        Returns:
            str: The converted PascalCase string.
        """
        # Split the string by changes from lowercase to uppercase letters and digits
        components = re.findall(r'[A-Z][a-z]*|[a-z]+|[0-9]+', name)
        # Capitalize the first letter of each component and join them
        return ''.join(x.capitalize() for x in components)