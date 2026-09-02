from datetime import datetime
from urllib.parse import unquote
from microsoft.fabric.hls.hds.claims_data_ingestions.cms_cclf.core.constants import CmsCclfConstants
from pyspark.sql import DataFrame
from pyspark.sql.functions import lit
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.utils.business_events_ingestion_handler import BusinessEventsIngestion
from microsoft.fabric.hls.hds.utils.dataframe_utils import append_to_delta_table_using_path
from microsoft.fabric.hls.hds.utils.utils import Utils as CommonUtils
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase
import uuid

def add_new_literal_column_for_input_value(input_df: DataFrame, column_name: str, val: str):
    """
    Add a new column with the specified literal value to the input DataFrame.
    Parameters:
    - input_df (DataFrame): The input DataFrame.
    - column_name (str): The name of the new column.
    - val (str): The literal value of the new column.
    Returns:
    - DataFrame: The input DataFrame with the new column.
    """
    return input_df.withColumn(colName=column_name, col=lit(val))

def remove_invalid_cms_cclf_files(self, df: DataFrame, to_path: str):
    """
    Removes invalid CMS CCLF files from the given DataFrame and moves them to the specified destination folder.
    Args:
        df (DataFrame): The DataFrame containing the CMS CCLF files.
        to_path (str): The destination folder path.
    Raises:
        Exception: If there is an error while moving the files.
    Returns:
        None
    """
    file_path_df = df.select(CmsCclfConstants.CMS_CCLF_FILE_PATH_NAME).distinct()
    lst = []
    id = str(uuid.uuid4())
    for row in file_path_df.collect():
        try:     
            invalid_files_path = unquote(row.filePath)
            move_file_to_folder(invalid_files_path, to_path, self._mssparkutils_client)
            message = LC.CMS_CCLF_INVALID_FILE_MOVES_TO_FAILED_FOLDER_MSG.format(file = invalid_files_path)
            self._logger.info(message)            
            new_row = self.business_events_ingestion_service.create_new_business_event_row(id=id,activityName= GC.CMSCCLF_CLAIMS_LANDINGZONE_TO_DELTATABLE_INGESTION_NOTEBOOK,targetFilePath=to_path, 
                                                    sourceFilePath=invalid_files_path, severity=GC.ERROR, 
                                                    eventType= GC.CMSCCLF_CLAIMS_INVALID_FILE, active=True, message= message,
                                                    exception= GC.CMSCCLF_CLAIMS_INVALID_FILE_EXCEPTION_MESSAGE)
            lst.append(new_row)            
        except Exception as e:
            self._logger.error(LC.FAILED_FILES_NOT_MOVED_ERR_MSG.format(
                error_msg=str(e)
            ))
    self.business_events_ingestion_service.insert_business_events(records=lst)
    
            
def max_file_size_validation(self, df: DataFrame, max_file_size_in_MB: int) -> list:
    """
    Validates the maximum file size of each file in the given DataFrame.
    Args:
        df (DataFrame): The DataFrame containing file information.
        max_file_size_in_MB (int): The maximum file size in megabytes.
    Returns:
        list: A list of file paths that exceed the maximum file size.
    """
    lst_max_file_size_path = []
    for files in df.collect():
        unquoted_file_path = unquote(files.filePath)
        file_details =  self._mssparkutils_client.fs_ls(unquoted_file_path)
        for file in file_details:
            file_size = file.size
            if file_size and file_size > (max_file_size_in_MB * 1024 * 1024):
                lst_max_file_size_path.append(files.filePath)
    return lst_max_file_size_path

@staticmethod
def move_file_to_folder(from_path: str, to_path: str,mssparkutils_client: MSSparkUtilsClientBase): 
    """
    Moves a file from the source path to the destination path.
    Args:
        from_path (str): The path of the file to be moved.
        to_path (str): The destination path where the file will be moved to.
        mssparkutils_client (MSSparkUtilsClientBase): The client object for MSSparkUtils.
        create_path (bool, optional): If True, creates the destination path if it doesn't exist. Defaults to False.
    """
    if not CommonUtils.path_exists(to_path, mssparkutils_client=mssparkutils_client):
        CommonUtils.create_folder(to_path, mssparkutils_client=mssparkutils_client)
    mssparkutils_client.fs_mv(from_path, to_path)
    
@staticmethod
def check_tables_exist(self, tables_list: list) -> bool:
    """
    This method checks if all the tables in the provided list exist in the Spark catalog.        
    :param table_names: List of table names to check.
    :return: True if all tables exist, False otherwise.
    """
    for delta_table in tables_list:
        if not self.spark.catalog.tableExists(delta_table, self.source_lakehouse_name):
            self._logger.error(LC.TABLE_NOT_FOUND_ERR_MSG.format(table_name= delta_table))
            return False
    return True

