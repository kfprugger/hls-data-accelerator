import uuid

from pyspark.sql import Column, DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DataType, StructType
from pyspark.sql.utils import AnalysisException

from common.utils.logging import Logger


class DataFrameUtils:

    @staticmethod
    def is_dataframe_cached(df: DataFrame) -> bool:
        return df.storageLevel.useDisk or \
            df.storageLevel.useMemory or \
            df.storageLevel.useOffHeap

    @staticmethod
    def convert_to_target_schema(df: DataFrame, target_schema: StructType) -> DataFrame:
        """converts a dataframe to a given target schema, including names and types of the columns
        the given df is expected to have all column names that the target schema has"""
        required_columns = []
        for column_name in target_schema.fieldNames():
            column_type = target_schema[column_name].dataType
            column = F.col(column_name).cast(column_type)
            required_columns.append(column)
        try:
            return df.select(*required_columns)
        except AnalysisException:
            Logger.error(f"Error while converting dataframe to target schema. required columns: {target_schema.fieldNames()}, "
                         f"existing columns: {df.columns}")
            raise

    @staticmethod
    def swap_columns(df: DataFrame, left_column_name: str, right_column_name: str) -> DataFrame:
        swap_column_name = "swap"

        df = df.select("*", F.col(left_column_name).alias(swap_column_name)).drop(left_column_name)
        df = df.select("*", F.col(right_column_name).alias(left_column_name)).drop(right_column_name)
        df = df.select("*", F.col(swap_column_name).alias(right_column_name)).drop(swap_column_name)

        return df

    @staticmethod
    def create_empty_df(spark: SparkSession, schema: StructType) -> DataFrame:
        return spark.createDataFrame(data=[], schema=schema)

    @staticmethod
    def is_empty(df: DataFrame) -> bool:
        return df._jdf.isEmpty()

    @staticmethod
    def is_not_empty(df: DataFrame) -> bool:
        return not DataFrameUtils.is_empty(df)

    @staticmethod
    def with_column_fast(df: DataFrame, column_name: str, column: Column) -> DataFrame:
        return df.select("*", column.alias(column_name))

    @staticmethod
    def with_column_renamed_fast(df: DataFrame, column_name: str, column_new_name: str) -> DataFrame:
        return DataFrameUtils.with_column_fast(df, column_new_name, F.col(column_name)).drop(column_name)

    @staticmethod
    def get_column_datatype(df: DataFrame, column_name: str) -> DataType:
        try:
            return df.schema[column_name].dataType
        except KeyError as ke:
            raise KeyError(f"Column {column_name} does not exist in the dataframe when trying to get column type") from ke


class RandomTempViewContext:
    """Creates a temporary view with a random name and drops it after the context is exited.
    usage:
    with RandomTempViewContext(spark, df) as view_name:
        spark.sql(f"SELECT * FROM {view_name}")
    """

    def __init__(self, spark: SparkSession, df: DataFrame):
        self.df = df
        self._spark = spark
        random_part = str(uuid.uuid4()).replace("-", "_")
        self.view_name = f"temp_view_{random_part}"

    def __enter__(self):
        self.df.createOrReplaceTempView(self.view_name)
        return self.view_name

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._spark.catalog.dropTempView(self.view_name)
