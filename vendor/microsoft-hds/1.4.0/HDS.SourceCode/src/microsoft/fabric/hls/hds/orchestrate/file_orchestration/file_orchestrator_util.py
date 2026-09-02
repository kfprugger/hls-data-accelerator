import os
from datetime import datetime
from pyspark.sql import SparkSession, DataFrame


class FileOrchestratorUtil:
    
    @staticmethod
    def get_current_date_in_utc() -> str :
        return datetime.utcnow().strftime("%Y/%m/%d")

    @staticmethod
    def get_current_timestamp_in_utc() -> str :
        return str(datetime.utcnow().timestamp())
    
    @staticmethod
    def read_files_with_spark(spark: SparkSession, source_path: str , file_extensions : list) -> DataFrame:
        """
        Read files from the given path using spark
        Args:
            spark (SparkSession): The spark session
            path (str): The path to read files from
        Returns:
            DataFrame: The dataframe containing the files
        """
        
        df = spark.read.format("binaryFile") \
            .option("recursiveFileLookup", "true") \
            .option("pathGlobFilter", "{" + ','.join(file_extensions) + "}") \
            .load(source_path) \
            .drop('content','modificationTime')
        return df
    
    @staticmethod
    def delete_empty_source_dir(source_mount_path: str):
        """
        Delete the source directory and nested directories if they are empty
        Args:
            source_mount_path (str): The source mount path
        """
        for root, dirs, files in os.walk(source_mount_path, topdown=False):
            for dir in dirs:
                dir_path = os.path.join(root, dir)
                if not os.listdir(dir_path):
                    os.rmdir(dir_path)