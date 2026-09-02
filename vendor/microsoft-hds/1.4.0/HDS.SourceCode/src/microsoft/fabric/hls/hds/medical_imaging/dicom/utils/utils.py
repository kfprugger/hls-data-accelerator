# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
"""
Module with a class containing static methods used through out the package
"""

from datetime import datetime
import os
from pyspark.sql import SparkSession
from pyspark.sql.streaming import DataStreamReader
from pyspark.sql.functions import *
from pyspark.sql.types import *
from typing import List, Tuple
from microsoft.fabric.hls.hds.medical_imaging.dicom.core.constants import ImagingStudyConstants as C
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.utils.dataframe_utils import find_managed_delta_table_using_path
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC

class Utils:
    """
    A class containing static methods used through out the package
    """

    @staticmethod
    def get_namespaces(mssparkutils_client: MSSparkUtilsClientBase, base_source_path: str, namespace: str) -> List[str]:
        """
        This method is used to get all the namespaces/source systems for which ingestion need to run
        If a namespace is explicitly passed then return that otherwise 
        all first level folder names under base_source_path

        Args:
            mssparkutils_client (MSSparkUtilsClientBase): mssparkutils client
            base_source_path (str): base source path
            namespace(str): the namespace explicitly passed to run ingestion on

        Returns:
            List[str]: list of namespaces/source systems
        """
        if namespace:
            return [namespace]
        
        namespaces = []
        for entry in mssparkutils_client.fs_ls(base_source_path):
            if entry.isDir:
                namespaces.append(entry.name)     
        return namespaces

    @staticmethod
    def repartition_df(df: DataFrame, batch_size: int, rows_per_partition: int) -> DataFrame:
        """
        This method is used to repartition a dataframe

        Args:
            df (DataFrame): dataframe to repartition
            batch_size (int): number of rows in the dataframe
            rows_per_partition (int): number of rows per partition

        Returns:
            DataFrame: repartitioned dataframe
        """
        
        if batch_size > 0 and rows_per_partition > 0 and batch_size > rows_per_partition:
            df = df.repartition(batch_size//rows_per_partition)
        return df
    
    @staticmethod
    def get_max_date_col_val(spark: SparkSession, 
                             delta_table_path: str, 
                             col_name: str, 
                             namespace: str, 
                             current_dataframe: DataFrame) -> datetime:
        """
        This method is used to fetch maximum value for a date column present in a delta table for a namespace
        and filtered by the inventory file path in the current dataframe

        Args:
            spark (SparkSession): spark session
            delta_table_path (str): path to the delta table
            col_name (str): column name in the delta table
            namespace (str): namespace value
            current_dataframe (DataFrame): the dataframe currently being processed

        Returns:
            datetime: maximum value for the column if found, minimum date possible otherwise
        """
        _DEFAULT_OLDER_DATE = datetime(1900, 1, 1)
        
        inventory_file_path = (
            current_dataframe
            .select(C.INVENTORY_FILE_PATH_COLUMN_NAME)
            .distinct()
            .first()
        )[0]

        # inventory_file_path = current_dataframe.select(C.INVENTORY_FILE_PATH_COLUMN_NAME).distinct().collect()
        # if len(inventory_file_path) > 1:
        #     raise ValueError(LC.MULTIPLE_INVENTORY_PROCESSING_ERR_MSG.format(
        #         inven_files_path=inventory_file_path
        #     ))
        
        try:
            delta_table_df = find_managed_delta_table_using_path(spark, delta_table_path).toDF()
            delta_table_df = delta_table_df.filter(
                (delta_table_df[C.SOURCE_SYSTEM_COLUMN_NAME] == namespace) & 
                (delta_table_df[C.INVENTORY_FILE_PATH_COLUMN_NAME] != inventory_file_path)
            )
            if delta_table_df.isEmpty():
                max_processed_date = _DEFAULT_OLDER_DATE
            else:    
                max_processed_date = delta_table_df.agg(max(col(col_name))).collect()[0][0]
            return max_processed_date
        except Exception as e:
            return _DEFAULT_OLDER_DATE
    
    @staticmethod
    def read_files_metadata_from_inventory(spark: SparkSession, 
                                           files_to_process_path:str,
                                           inventory_files_path: str,
                                           azure_blob_storage_inventory: bool,
                                           max_files_per_trigger:int,
                                           max_bytes_per_trigger:int) -> DataStreamReader:
    
        """
        This method is used to read the files metadata from inventory into a streaming dataframe
        
        Args:
            spark (SparkSession): spark session
            files_to_process_path (str): path where files are located
            inventory_files_path (str): path where inventory files are located
            azure_blob_storage_inventory (bool): boolean indicating whether it is azure blob storage inventory or not, to support pre-processing Azure blob storage inventory OOB
            max_files_per_trigger (int): maximum number of files to process per micro-batch
            max_bytes_per_trigger (int): maximum bytes of data to process per micro-batch
        """    

        if azure_blob_storage_inventory:
            df_schema = StructType([
                StructField(C.AZ_INVEN_NAME_FIELD, StringType(), False),
                StructField(C.AZ_INVEN_LAST_MODIFIED_FIELD, LongType(), False),
                StructField(C.AZ_INVEN_IS_FOLDER_FIELD, BooleanType(), True)
            ])
            
            df_stream = (
                spark.readStream.schema(df_schema)
                .option("pathGlobFilter", '*.parquet')
                .option("recursiveFileLookup", True)
                .option("maxFilesPerTrigger", max_files_per_trigger)
                .option("maxBytesPerTrigger", max_bytes_per_trigger) 
                .parquet(inventory_files_path)
                .filter(col(C.AZ_INVEN_NAME_FIELD).contains(f".dcm") & col(C.AZ_INVEN_IS_FOLDER_FIELD).isNull())
                .drop(C.AZ_INVEN_IS_FOLDER_FIELD)
                .withColumnRenamed(C.AZ_INVEN_NAME_FIELD, C.FILE_PATH_COLUMN_NAME)
                .withColumnRenamed(C.AZ_INVEN_LAST_MODIFIED_FIELD, C.SOURCE_MODIFIED_COLUMN_NAME)
                .withColumn(C.SOURCE_MODIFIED_COLUMN_NAME, from_unixtime(col(C.SOURCE_MODIFIED_COLUMN_NAME)/1000).cast(TimestampType()))
            )
            
        else:
            df_schema = StructType([
                StructField(C.FILE_PATH_COLUMN_NAME, StringType(), False),
                StructField(C.SOURCE_MODIFIED_COLUMN_NAME, TimestampType(), False)
            ])

            df_stream = (
                spark.readStream.schema(df_schema)
                .option("pathGlobFilter", '*.parquet')
                .option("recursiveFileLookup", True)
                .option("maxFilesPerTrigger", max_files_per_trigger)
                .option("maxBytesPerTrigger", max_bytes_per_trigger) 
                .parquet(inventory_files_path)
            )
        
        return ( df_stream
                .withColumn(C.FILE_PATH_COLUMN_NAME, concat(lit(f"{files_to_process_path}/"), col(C.FILE_PATH_COLUMN_NAME)))
                .withColumn(C.INVENTORY_FILE_PATH_COLUMN_NAME, input_file_name())
                .withColumn(C.INVENTORY_FILE_PATH_COLUMN_NAME, regexp_extract(C.INVENTORY_FILE_PATH_COLUMN_NAME, "(.*/)", 1))
            )

    @staticmethod
    def read_files_to_df_stream(spark: SparkSession, files_to_process_path: str, max_files_per_trigger: int) -> DataStreamReader:
        """
        This method is used to read files in binary format into a streaming dataframe

        Args:
            spark (SparkSession): spark session
            files_to_process_path (str): path where files are located
            max_files_per_trigger (int): maximum number of files to process per micro-batch

        Returns:
            DataStreamReader: streaming dataframe containing files details
        """
        df_schema = StructType([
            StructField(C.PATH_ATTR_NAME, StringType(), True),
            StructField(C.MODIFICATION_TIME_ATTR_NAME, TimestampType(), True),
            StructField(C.LENGTH_ATTR_NAME, LongType(), True),    
            StructField(C.DCM_FILE_CONTENT_ATTR_NAME, BinaryType(), True)
        ])
        
        return (
            spark.readStream.format('binaryFile')
            .schema(df_schema)
            .option("pathGlobFilter", '*.dcm')   
            .option("maxFilesPerTrigger", max_files_per_trigger)
            .option("recursiveFileLookup", True)
            .option("basePath", files_to_process_path)       
            .load(files_to_process_path)
            .drop(C.LENGTH_ATTR_NAME, C.DCM_FILE_CONTENT_ATTR_NAME)
            .withColumnRenamed(C.PATH_ATTR_NAME, C.FILE_PATH_COLUMN_NAME)
            .withColumnRenamed(C.MODIFICATION_TIME_ATTR_NAME, C.SOURCE_MODIFIED_COLUMN_NAME)
        )

    @staticmethod
    def get_current_date_in_utc() -> str :
        return datetime.utcnow().strftime("%Y/%m/%d")

    @staticmethod
    def get_current_timestamp_in_utc() -> str :
        return str(datetime.utcnow().timestamp())

    @staticmethod
    def move_files(from_path: str, to_path: str, mssparkutils_client: MSSparkUtilsClientBase, create_path : bool = False):
        mssparkutils_client.fs_mv(from_path, to_path, create_path)
        return from_path

    @staticmethod
    def set_hadoop_default_path(spark: SparkSession,lakehouse_path : str):
        spark._jsc.hadoopConfiguration().set("fs.defaultFS", lakehouse_path)
        
    @staticmethod
    def get_table_fields_schema(tables_schema : dict, table_name : str):
        field_schema = tables_schema[table_name]['schema']
        schema_details = StructType.fromJson(field_schema)    
        return schema_details
    
    @staticmethod
    def get_fields_name(tables_schema : dict, table_name : str):
        schema_details = Utils.get_table_fields_schema(tables_schema, table_name)
        return schema_details.fieldNames()

    @staticmethod
    def get_chkpt_path_based_on_source(base_path: str, source_path_pattern: str):
        #remove wild card character "*" from the source path pattern (if any)
        source_path_pattern = source_path_pattern.split("*")[0]
        #remove the string before "//"
        source_path_pattern = source_path_pattern.split("//")[-1]
        return os.path.join(base_path, source_path_pattern)
    
    @staticmethod
    def get_field_type_with_tags_not_null(tables_schema: dict, table_name: str, ignore_list: list = []) -> dict:
        schema_details = Utils.get_table_fields_schema(tables_schema, table_name)
        field_by_name = {}
        for field in schema_details.fields:
            metadata = getattr(field, 'metadata', {})
            column_name = metadata.get('columnName', None)
            tag = metadata.get('tag', None)
            if column_name and tag and column_name.lower() not in [y.lower() for y in ignore_list]:
                field_by_name[column_name] = field
        return field_by_name
    
    @staticmethod
    def get_fields_by_keys(tables_schema: dict, table_name: str, keys: List[str]) -> Tuple[dict, dict]:
        """
        Returns two dictionaries containing all fields where the columnName in metadata matches any of the keys (case-insensitive).
        One dictionary for complex types (Array, Map) and one for regular types.

        Args:
            tables_schema (dict): The schema definition for the tables.
            table_name (str): The name of the table to get fields from.
            keys (list): The column names to match.

        Returns:
            (dict, dict): A tuple of two dictionaries: (regular_fields, complex_fields).
        """
        schema_details = Utils.get_table_fields_schema(tables_schema, table_name)
        regular_field_by_name = {}
        complex_field_by_name = {}
        lower_keys = [key.lower() for key in keys]
        complex_types = (ArrayType, MapType)

        for field in schema_details.fields:
            metadata = getattr(field, 'metadata', {})
            column_name = metadata.get('columnName', None)
            if column_name and column_name.lower() in lower_keys:
                if isinstance(field.dataType, complex_types):
                    complex_field_by_name[column_name] = field
                else:
                    regular_field_by_name[column_name] = field
        return regular_field_by_name, complex_field_by_name