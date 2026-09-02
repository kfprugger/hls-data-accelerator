from pyspark.sql import SparkSession, DataFrame

class DeltaTableStreamReader:

    """
    DeltaTable Stream Reader service for reading a delta table using spark structured streaming 
    """

    def __init__(self,
    spark: SparkSession, **kwargs):

        """
        Initialize DeltaTableStreamReader
        Args:
            - kwargs: dict - An optional dictionary of options to be set on the stream. See here for a list of options available - https://docs.databricks.com/structured-streaming/delta-lake.html
                - maxFilesPerTrigger: How many new files to be considered in every micro-batch. The default is 1000.
                - maxBytesPerTrigger: How much data gets processed in each micro-batch. This option sets a “soft max”, meaning that a batch processes 
                                      approximately this amount of data and may process more than the limit in order to make the streaming query move
                                      forward in cases when the smallest input unit is larger than this limit. This is not set by default.
                - skipChangeCommits: str - "true" to skip change commits, "false" to throw an exception on data modifying changes
        """

        self.spark = spark
        self.kwargs = kwargs

    def set_up_streaming(self, delta_table_path:str) -> DataFrame:
        """
        Set up streaming on a delta table

        Args:
            - delta_table_path: The path to the delta table
        Returns: 
            - A streaming Dataframe
        """
        delta_stream_reader = self.spark.readStream.format("delta")
        for option, value in self.kwargs.items():
            delta_stream_reader = delta_stream_reader.option(option, value)

        return delta_stream_reader.load(delta_table_path)
