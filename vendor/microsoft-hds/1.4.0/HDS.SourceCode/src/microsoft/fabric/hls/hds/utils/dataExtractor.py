from pyspark.sql.types import StructType, StructField, StringType, ArrayType, MapType
from pyspark.sql import SparkSession
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.utils.logging_helper import LoggingHelper

class DataExtractor:
    """
    A class that extracts data from text files and processes it.

    Args:
        spark (SparkSession): The Spark session object.
    Attributes:
        spark (SparkSession): The Spark session object.
        _logger (Logger): The logger object for logging.
    """

    def __init__(self, spark: SparkSession):
        """
        Initializes the DataExtractor object.

        Args:
            spark (SparkSession): The SparkSession object.

        Returns:
            None
        """
        self.spark = spark
        self._logger = LoggingHelper.get_generic_logger(self.spark, self.__class__.__name__, GlobalConstants.LOGGING_LEVEL)

            
    def read_data_files_to_df_stream(self, file_path, max_files_per_trigger: int):
        """
        Reads data files from the specified file path into a streaming DataFrame.
        Args:
            file_path (str): The path to the data files.
            max_files_per_trigger (int): maximum number of files to process per micro-batch.
        Returns:
            pyspark.sql.DataFrame: A streaming DataFrame containing the data from the files.
        """                
        self._logger.info(LC.READ_STREAM_PROCESS_INFO_MSG.format(state= LC.SPARK_READ_STARTED,
                                                                      drop_folder=file_path))
        
        df_schema = StructType([
            StructField(GlobalConstants.CLAIMS_ROW_VALUE, StringType(), True)
        ])
        
        return (
            self.spark.readStream.format('text')
                .schema(df_schema)
                .option("maxFilesPerTrigger", max_files_per_trigger)
                .option("recursiveFileLookup", True)
                .load(file_path)
            )
    def read_json_files_to_df_stream(self, file_path, max_files_per_trigger: int):
        """
        Reads JSON files containing an array of objects and converts them into a structured streaming DataFrame.
        
        Args:
            file_path (str): Path to the JSON files.
            max_files_per_trigger (int): Number of files processed per batch.

        Returns:
            pyspark.sql.DataFrame: Streaming DataFrame with parsed JSON objects.
        """
        self._logger.info(LC.READ_STREAM_PROCESS_INFO_MSG.format(state= LC.SPARK_READ_STARTED,
          
                                                                      drop_folder=file_path))
    
        batch_df = self.spark.read \
            .option("multiline", "true") \
            .option("recursiveFileLookup", "true") \
            .json(file_path)
            
        schema = batch_df.schema

        df = (self.spark.readStream
                    .schema(schema)
                    .format("json") 
                    .option("multiline","true")
                    .option("maxFilesPerTrigger", max_files_per_trigger)
                    .option("recursiveFileLookup", True)
                    .load(file_path))

        return df