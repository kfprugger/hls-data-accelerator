from ctypes import Structure
from typing import Union
from pyspark.sql import SparkSession, DataFrame

class FileStreamReader:
    def __init__(self, spark: SparkSession, **kwargs):
        """
        Args:
        spark: spark session
        """
        self.spark: SparkSession = spark
        self.kwargs = kwargs

    def set_up_streaming_json(self, schema: Union[Structure|str|None], streaming_path: str) -> DataFrame:
        """
        Given the streaming path and a schema path, this function will
        set up the initial configuration for reading data via streaming

        Args:
            schema: schema object
            streaming_path: streaming path

        Returns:
            DataFrame: a streaming Dataframe
        """
        # set up streaming
        data_stream_reader = self.spark.readStream.schema(schema)
        # apply any additional options (max_files_per_trigger, etc.)
        for option, value in self.kwargs.items():
            data_stream_reader = data_stream_reader.option(option, value)

        # loads the JSON file stream and returns as a DF
        file_streaming_df = data_stream_reader.json(streaming_path)

        return file_streaming_df  # type: ignore
    

    def set_up_streaming_text_file(self, streaming_path: str) -> DataFrame:
        """
        Given the streaming path this function will
        set up the initial configuration for reading data via streaming

        Args:
            streaming_path: streaming path
        Returns:
            DataFrame: a streaming Dataframe
        """
        # set up streaming
        data_stream_reader = self.spark.readStream
        # apply any additional options (max_files_per_trigger, etc.)
        for option, value in self.kwargs.items():
            data_stream_reader = data_stream_reader.option(option, value)

        # loads the text file stream and returns as a DF
        file_streaming_df = data_stream_reader.text(streaming_path)

        return file_streaming_df
        

    def set_up_streaming_csv(
        self, schema: Union[Structure|str|None], streaming_path: str, delimiter: str = "\t") -> DataFrame:
        """
        Given the streaming path and a schema path, this function will
        set up the initial configuration for reading data via streaming

        Args:
            schema (Union[Structure|str|None]): The schema
            streaming_path (str): streaming path
            delimiter (str): delimiter

        Returns:
            DataFrame: a streaming Dataframe
        """
        # set up streaming
        data_stream_reader = self.spark.readStream
        # apply any additional options (max_files_per_trigger, etc.)
        for option, value in self.kwargs.items():
            data_stream_reader = data_stream_reader.option(option, value)

        # loads the JSON file stream and returns as a DF
        file_streaming_df = data_stream_reader.options(
            header="True", delimiter=delimiter
        ).csv(path=streaming_path, schema=schema)

        return file_streaming_df  # type: ignore
    
    def set_up_streaming_ndjson_string(self, streaming_path: str) -> DataFrame:
        """
        Given the streaming path, this function will
        set up the initial configuration for reading data via streaming

        Args:
            streaming_path: streaming path

        Returns:
            DataFrame: a streaming Dataframe
        """
        # set up streaming
        data_stream_reader = self.spark.readStream

        # apply any additional options (max_files_per_trigger, etc.)
        for option, value in self.kwargs.items():
            data_stream_reader = data_stream_reader.option(option, value)
        # Read the ndjson file as a text stream
        file_streaming_df = data_stream_reader.text(streaming_path)

        return file_streaming_df
