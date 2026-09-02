# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
"""
DataFrame utilities
"""
import re
from typing import Any, List, Optional, Union
from pyspark.sql import DataFrame, Column, SparkSession, Window
from pyspark.sql.types import StructType, ArrayType, TimestampType, StructField, MapType
from pyspark.sql import functions as F
from pyspark.sql.functions import col, current_timestamp, desc, row_number, expr, to_json, when, regexp_extract, lit
from pyspark.sql.utils import AnalysisException
from delta import DeltaTable
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.flatten.normalization.normalization_manager import FlattenNormalization
from microsoft.fabric.hls.hds.flatten.constants import FlattenConstants as C
from microsoft.fabric.hls.hds.utils.data_manager_logger import DataManagerLogger
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase
from microsoft.fabric.hls.hds.execution_metrics.base_metrics_collector import BaseMetricsCollector

def flatten_struct(
    input_df: DataFrame,
    struct_column_name: str,
    flattened_columns_prefix: str,
    keep_struct_column: bool = False,
) -> DataFrame:
    """
    Flatten structure type
    Arguments:
    - struct_column_name:str - name of the column to flatten
    - flattened_columns_prefix:str - prefix before names of struct type in result dataframe
    - keep_struct_column:bool - should we remove column to flatten or not

    Returns:
    - pyspark.sql.DataFrame - flattened dataframe
    """
    existing_columns: List[Column] = [
        col("`" + c[0] + "`")
        for c in input_df.dtypes
        if (keep_struct_column | ("`" + c[0] + "`" != "`" + struct_column_name + "`"))
    ]
    flattened_columns: List[Column] = [
        col("`" + struct_column_name + "`" + "." + c).alias(
            flattened_columns_prefix + c
        )
        for c in input_df.select("`" + struct_column_name + "`" + ".*").columns
    ]

    return input_df.select(existing_columns + flattened_columns)

def stringify_complex_types(input_df: DataFrame) -> DataFrame:
    """
    Stringify the complex field types and append them as new
    columns with postfix "_string" in the dataframe

    Args:
    - input_df: DataFrame - Dataframe for processing.
    """

    # get all the complex type fields in the dataframe like array, structs
    complex_fields = [
        field.name
        for field in input_df.schema.fields
        if isinstance(field.dataType, ArrayType)
        or isinstance(field.dataType, StructType)
        or isinstance(field.dataType, MapType)
    ]

    return input_df.select(
        [col("*")]
        + [
            to_json(col(colname), options={"ignoreNullFields": False}).alias(
                f"{colname}_string"
            )
            for colname in complex_fields
        ]
    )


def flatten_all_dataframe_struct(input_df: DataFrame) -> DataFrame:
    """Flatten a dataframe complex type (StructType) with nested columns.
    It will check that generated column names are unique.
    Arguments:
    - input_df: pyspark.sql.DataFrame - dataframe to flatten

    Returns:
    - pyspark.sql.DataFrame - flattened dataframe
    """

    def generate_unique_column(proposed_name, input_columns):
        """Generate a unique column name."""
        if proposed_name not in input_columns:
            return proposed_name
        else:
            return generate_unique_column(proposed_name + "_", input_columns)

    # get the complex fields of StructType in the dataframe
    complex_fields = dict(
        [
            (field.name, field.dataType)
            for field in input_df.schema.fields
            if isinstance(field.dataType, StructType)
        ]
    )

    # flatten the complex fields
    for col_name, complex_field in complex_fields.items():
        expanded = [
            col("`" + col_name + "`" + "." + k).alias(
                generate_unique_column(col_name + "_" + k, input_df.columns)
            )
            for k in [n.name for n in complex_field]
        ]

        input_df = input_df.select("*", *expanded)
    return input_df


def drop_flattened_columns(
    input_df: DataFrame, struct_column_name: str, flattened_columns_prefix: str
) -> DataFrame:
    """
    Drop columns received after flattening with func flatten_struct
    """
    flattened_columns: List[str] = [
        flattened_columns_prefix + c
        for c in input_df.select(struct_column_name + ".*").columns
    ]

    return input_df.drop(*flattened_columns)


def sanitize_df_columns(input_df: DataFrame) -> DataFrame:
    """
    # We may need to replace '.' with '_' in column names to avoid
    # the error mentioned here - https://mungingdata.com/pyspark/avoid-dots-periods-column-names/
    """
    sanitized_cols = (column.replace(".", "_") for column in input_df.columns)
    return input_df.toDF(*sanitized_cols)

def sanitize_schema(schema: StructType) -> StructType:
    """
    Sanitizes the given schema by replacing column names and recursively sanitizing nested schemas.

    Args:
    schema (StructType): The schema to sanitize.

    Returns:
    StructType: The sanitized schema.
    """
    return StructType([
    StructField(sanitize_column_name(field.name), 
            sanitize_schema(field.dataType) if isinstance(field.dataType, StructType) else field.dataType, 
            field.nullable) 
    for field in schema.fields
    ])

def sanitize_column_name(name: str) -> str:
    """
    Sanitizes the given column name by replacing spaces and slashes with underscores,
    and removing parentheses, single quotes, and dots.

    Args:
        name (str): The column name to sanitize.

    Returns:
        str: The sanitized column name.
    """
    name = re.sub(r"[ /]", "_", name)
    name = re.sub(r"[()'.]", "", name)
    return name


def encode_df_string(input_str: str) -> str:
    """
    Encodes with ` column names with dot(.) in it
        in case string already encoded - it will return it as is
        in case string representing an expression - it will return as is

    Used to encode value which can represent both: columns or expressions
    """
    # already encoded
    if "`" in input_str:
        return input_str
    # match definition of variable with '.' (dots)
    if re.match(pattern=r"^(\w+)(\.\w+)+$", string=input_str):
        return f"`{input_str}`"
    return input_str


def find_managed_delta_table_using_path(
    spark_session: SparkSession, delta_table_path: str
) -> Union[DeltaTable, None]:
    """
    Finds managed delta table by name and database

    Normally we should successfully get DeltaTable object by name, but in case of local
    development and using from a different thread we may not be able to find it by name.
    The same time delta table exists in the database and we can find it by location.

    Arguments:
        - spark_session : SparkSession - spark session to access resources/files/load dataframes
        - delta_table_path : str - The path where the Delta table resides or should be created.

    Returns:
        - DeltaTable - delta table object or None if unable to find
    """
    delta_result = None

    try:
        delta_result = DeltaTable.forPath(spark_session, delta_table_path)
    except AnalysisException:
        return delta_result
    return delta_result

def is_delta_table_empty(spark: SparkSession, table_path: str):
    """Check if delta table is empty

    Args:
        spark: spark session
        table_path (str): the path to the delta table

    Returns:
        _type_: _description_
    """
    delta_table = DeltaTable.forPath(spark, table_path)
    return delta_table.toDF().isEmpty()

def create_delta_table_managed_using_path(
    df_to_process: DataFrame,
    delta_table_path: str):
    """Create managed delta table from the dataframe
    
    Args:
        df_to_process (DataFrame): The dataframe to use to create the delta table
        delta_table_path (str): The path where the Delta table resides or should be created.
    """
    
    delta_table_df = df_to_process.limit(0)
    # Create managed delta table from the dataframe
    delta_table_df.write.format("delta").mode(
        "overwrite").save(delta_table_path)

def get_or_create_managed_delta_table_using_path(spark_session: SparkSession,
                                      data_manager_logger: DataManagerLogger,
                                      df_to_process: DataFrame,
                                      delta_table_path: str):
    """
    Retrieves an existing managed Delta table or creates a new one if it doesn't exist.
    
    Parameters:
    - spark_session (SparkSession): The active Spark session.
    - delta_table_path (str): The path where the Delta table resides or should be created.
    - df_to_process (DataFrame): The DataFrame used to create the Delta table if it doesn't exist.
    
    Returns:
    - DeltaTable: The retrieved or newly created Delta table.
    
    Raises:
    - ValueError: If the Delta table cannot be created or retrieved.
    """
    # Try to get Delta table if it exists, otherwise create it
    try:
        delta_table = find_managed_delta_table_using_path(spark_session=spark_session,
                                               delta_table_path=delta_table_path)
    except AnalysisException:
        delta_table = None

    # If we can't find it, let's create it
    if not delta_table:
        create_delta_table_managed_using_path(delta_table_path=delta_table_path,
                                   df_to_process=df_to_process)
        try:
            delta_table = find_managed_delta_table_using_path(spark_session=spark_session,
                                                   delta_table_path=delta_table_path)
        except AnalysisException:
            delta_table = None

    if not delta_table:
        data_manager_logger.error(
            f"{LC.CREATING_AND_FINDING_DATABASE_ERR_MSG} {delta_table_path}")
        raise ValueError(
            f"{LC.CREATING_AND_FINDING_DATABASE_ERR_MSG} {delta_table_path}")

    return delta_table

def find_managed_delta_table_using_name(
    spark_session: SparkSession, delta_table_name: str, delta_database: Union[str, None]
) -> Union[DeltaTable, None]:
    """
    Finds managed delta table by name and database

    Normally we should successfully get DeltaTable object by name, but in case of local
    development and using from a different thread we may not be able to find it by name.
    The same time delta table exists in the database and we can find it by location.

    Arguments:
        - spark_session : SparkSession - spark session to access resources/files/load dataframes
        - delta_table_name : str - name of the delta table, where to save dataframe
        - delta_database : str - name of the database, where delta table is located

    Returns:
        - DeltaTable - delta table object or None if unable to find
    """
    delta_result = None

    # Construct full Delta table name
    full_delta_table_name = (
        f"`{delta_database}`.`{delta_table_name}`"
        if delta_database
        else f"`{delta_table_name}`"
    )

    try:
        delta_result = DeltaTable.forName(spark_session, full_delta_table_name)
    except AnalysisException:
        # lets see if we can find it in the database
        # todo: check in the next version of Delta Lake if we can find it by name
        list_tables = spark_session.catalog.listTables(delta_database)
        if list_tables:
            if delta_table_name in [table.name for table in list_tables]:
                # find details about location fo the delta table
                location = (
                    spark_session.sql(f"DESCRIBE DETAIL {full_delta_table_name}")
                    .select("location")
                    .collect()[0][0]
                )
                if location:
                    delta_result = DeltaTable.forPath(spark_session, location)
    return delta_result


def create_delta_table_managed_using_name(
    df_to_process: DataFrame,
    delta_table_name: str,
    delta_database: Union[str, None] = None,
):
    """
    Create managed delta table from the dataframe
    (location is specified by delta_database and delta_table_name)
    """
    # Construct full Delta table name
    full_delta_table_name = (
        f"`{delta_database}`.`{delta_table_name}`"
        if delta_database
        else f"`{delta_table_name}`"
    )
    delta_table_df = df_to_process.limit(0)
    # Create managed delta table from the dataframe
    delta_table_df.write.format("delta").mode(
        "overwrite").saveAsTable(full_delta_table_name)

def get_or_create_managed_delta_table_using_name(spark_session: SparkSession,
                                      data_manager_logger: DataManagerLogger,
                                      df_to_process: DataFrame,
                                      delta_table_name: str,
                                      delta_database: Union[str, None] = None):
    """
    Retrieves an existing managed Delta table or creates a new one if it doesn't exist.
    
    Parameters:
    - spark_session (SparkSession): The active Spark session.
    - delta_database (str): The name of the database where the Delta table resides or should be created.
    - delta_table_name (str): The name of the Delta table to retrieve or create.
    - df_to_process (DataFrame): The DataFrame used to create the Delta table if it doesn't exist.
    
    Returns:
    - DeltaTable: The retrieved or newly created Delta table.
    
    Raises:
    - ValueError: If the Delta table cannot be created or retrieved.
    """
    # Construct full Delta table name for error logging
    full_delta_table_name = f"`{delta_database}`.`{delta_table_name}`" if delta_database else f"`{delta_table_name}`"

    # Try to get Delta table if it exists, otherwise create it
    try:
        delta_table = find_managed_delta_table_using_name(spark_session=spark_session,
                                               delta_table_name=delta_table_name,
                                               delta_database=delta_database)
    except AnalysisException:
        delta_table = None

    # If we can't find it, let's create it
    if not delta_table:
        create_delta_table_managed_using_name(delta_database=delta_database,
                                   delta_table_name=delta_table_name,
                                   df_to_process=df_to_process)
        try:
            delta_table = find_managed_delta_table_using_name(spark_session=spark_session,
                                                   delta_table_name=delta_table_name,
                                                   delta_database=delta_database)
        except AnalysisException:
            delta_table = None

        if not delta_table:
            data_manager_logger.error(
                f"{LC.CREATING_AND_FINDING_DATABASE_ERR_MSG} {full_delta_table_name}")
            raise ValueError(
                f"{LC.CREATING_AND_FINDING_DATABASE_ERR_MSG} {full_delta_table_name}")

    return delta_table

def add_current_timestamp_column(input_df: DataFrame, column_name: str):
    """
    Add a new column with the current timestamp to the DataFrame.

    Parameters:
    - df: The input DataFrame.
    - column_name: The name of the new column.

    Returns:
    - DataFrame with the new column.
    """
    
    return input_df.withColumn(column_name, current_timestamp())

def add_normalized_current_timestamp_column(spark_session: SparkSession, 
                                            input_df: DataFrame,
                                            column_name: str):
    """
    Add a new column with the current timestamp to the DataFrame.

    Parameters:
    - df: The input DataFrame.
    - column_name: The name of the new column.

    Returns:
    - DataFrame with the new normalized timestamp column.
    """
    def __check_udf_registered(udf_name: str) -> bool:
        try:
            # Use SQL to check if the UDF exists (works if it's globally registered)
            result = spark_session.sql(f"SHOW FUNCTIONS LIKE '{udf_name}'").collect()
            return len(result) > 0
        except Exception as e:
            print(f"Error checking UDF registration: {e}")
            return False
    
    if not __check_udf_registered(C.NORM_UDF_NORM_DATE):
        spark_session.udf.register(
            C.NORM_UDF_NORM_DATE, FlattenNormalization.normalize_date, TimestampType())

    # Add a new column with the current timestamp to the DataFrame.
    input_df = add_current_timestamp_column(input_df=input_df, column_name=column_name)
    
    # Normalize the timestamp column
    norm_expression = f"{C.NORM_UDF_NORM_DATE}(`{column_name}`)"
    
    return input_df.withColumn(colName=column_name, col=expr(norm_expression))

def append_unique_to_delta_managed_using_name(spark_session: SparkSession,
                                   data_manager_logger: DataManagerLogger,
                                   df_to_process: DataFrame,
                                   delta_table_name: str,
                                   unique_columns: List[str],
                                   delta_database: Union[str, None] = None):
    """
    Append a dataframe to managed delta table (inserts only new rows)
    (location is specified by delta_database and delta_table_name)

    Arguments:
    - spark_session : SparkSession - spark session to access resources/files/load dataframes
    - data_manager_logger : DataManagerLogger - logger to log messages
    - df_to_process : DataFrame - dataframe to save
    - delta_table_name : str - name of the delta table, where to save dataframe
    - unique_columns : List[str] - a set of columns that uniquely identify a row.
        The same set of these columns in the row will not be updated in delta table
    - delta_database : str (optional) - name of the delta database, where to save dataframe.
    It is optional, if not specified, delta table will be saved in the default database
    default database is specified in spark.sql.defaultDatabase property like
    `spark_session.conf.set("spark.sql.catalog.spark_catalog.currentDatabase", delta_database)`
    """

    # Try to get Delta table if it exists, otherwise create it
    delta_table = get_or_create_managed_delta_table_using_name(spark_session=spark_session,
                                                    data_manager_logger=data_manager_logger,
                                                    df_to_process=df_to_process,
                                                    delta_table_name=delta_table_name,
                                                    delta_database=delta_database
                                                    )
    
    if not unique_columns:
        data_manager_logger.error(LC.EMPTY_UNIQUE_COLUMNS_INPUT_ERR_MSG)
        raise ValueError(LC.EMPTY_UNIQUE_COLUMNS_INPUT_ERR_MSG)

    merge_condition = " AND ".join(
        f"delta_table.{col_name} IS NOT DISTINCT FROM df_to_process.{col_name}"
        for col_name in unique_columns
    )

    # Create a list of values for the INSERT clause
    value_list = {f"`{col}`": f"df_to_process.`{col}`" for col in df_to_process.columns}

    delta_table.alias("delta_table").merge(
        df_to_process.alias("df_to_process"), merge_condition
    ).whenNotMatchedInsert(values=value_list).execute()  # type: ignore
    
def append_unique_to_delta_managed_using_path(spark_session: SparkSession,
                                   data_manager_logger: DataManagerLogger,
                                   df_to_process: DataFrame,
                                   unique_columns: List[str],
                                   delta_table_path: str):
    """
    Append a dataframe to managed delta table (inserts only new rows)
    (location is specified by delta_database and delta_table_name)

    Arguments:
    - spark_session : SparkSession - spark session to access resources/files/load dataframes
    - data_manager_logger : DataManagerLogger - logger to log messages
    - df_to_process : DataFrame - dataframe to save
    - unique_columns : List[str] - a set of columns that uniquely identify a row.
        The same set of these columns in the row will not be updated in delta table
    - delta_table_path : str - The path to the delta database
    """

    # Try to get Delta table if it exists, otherwise create it
    delta_table = get_or_create_managed_delta_table_using_path(spark_session=spark_session,
                                                    data_manager_logger=data_manager_logger,
                                                    df_to_process=df_to_process,
                                                    delta_table_path=delta_table_path
                                                    )
    if not unique_columns:
        data_manager_logger.error(
            LC.EMPTY_UNIQUE_COLUMNS_INPUT_ERR_MSG)
        raise ValueError(LC.EMPTY_UNIQUE_COLUMNS_INPUT_ERR_MSG)

    merge_condition = ' AND '.join(
            f"delta_table.{col_name} = df_to_process.{col_name}" for col_name in unique_columns)

    delta_table.alias("delta_table").merge(
        source=df_to_process.alias("df_to_process"), condition=merge_condition
    ).whenNotMatchedInsertAll().execute()  # type: ignore


def upsert_unique_to_delta_managed(spark_session: SparkSession,
                                    data_manager_logger: DataManagerLogger,
                                    df_to_process: DataFrame,
                                    delta_table_path: str,
                                    unique_columns: List[str],
                                    **kwargs):
    """
    Upserts data from a source DataFrame into a Delta table based on unique columns. 
    The dataframe should only contain unique records
    
    Parameters:
    - spark_session: Active Spark session.
    - data_manager_logger: Logger for capturing logs.
    - df_to_process: Source DataFrame to be upserted.
    - delta_table_path: The path to the target delta table.
    - unique_columns: List of columns that define uniqueness for upsert.
    - delta_database: Optional database name where the Delta table resides.
    - kwargs: dict - An optional dictionary of keyword arguments 
            to pass to the upsert_unique_to_delta_managed:
                - source_modified_on_column: Timestamp column of when the source data was last modified. 
                Used to identify the latest version of the source data. Default is 'meta_lastUpdated'
                - collect_metrics_fn: Callable - A function to collect metrics for the operation

    Returns:
    None
    """
    
    collect_metrics_fn = kwargs.get("collect_metrics_fn", None)
    # Add the normalized msftModifiedDatetime and msftCreatedDatetime column with the current timestamp
    # we need to add it at the beginning of the process to ensure delta schema will have it
    df_to_process = add_normalized_current_timestamp_column(spark_session=spark_session,
                                                            input_df=df_to_process,
                                                            column_name=GC.DEFAULT_SILVER_MODIFIED_DATE_COL)
    
    df_to_process = add_normalized_current_timestamp_column(spark_session=spark_session,
                                                            input_df=df_to_process,
                                                            column_name=GC.DEFAULT_SILVER_FHIR_TABLE_MSFT_CREATED_DATE_COL)
    
    df_to_process_columns = df_to_process.columns
        
    # By default 'meta_lastUpdated' is the timestamp column for Silver tables
    source_timestamp_column = kwargs.get("source_modified_on_column", GC.DEFAULT_SOURCE_MODIFIED_ON_COLUMN)
    
    # Ensure msftModifiedDatetime is the first column for indexing
    if GC.DEFAULT_SILVER_MODIFIED_DATE_COL in df_to_process_columns:
        columns = [GC.DEFAULT_SILVER_MODIFIED_DATE_COL] + [col for col in df_to_process_columns if col != GC.DEFAULT_SILVER_MODIFIED_DATE_COL]
        df_to_process = df_to_process.select(columns)
    
    delta_table = get_or_create_managed_delta_table_using_path(spark_session=spark_session,
                                                        data_manager_logger=data_manager_logger,
                                                        df_to_process=df_to_process,
                                                        delta_table_path=delta_table_path
                                                        )
    # Check if DataFrame is empty
    if df_to_process.isEmpty():
        data_manager_logger.debug(LC.UPSERT_UNIQUE_TO_DELTA_MANAGED_SKIPPED.format(
            delta_table_path=delta_table_path)
        )
        return
    
    if not unique_columns:
        data_manager_logger.error(LC.EMPTY_UNIQUE_COLUMNS_INPUT_ERR_MSG)
        raise ValueError(LC.EMPTY_UNIQUE_COLUMNS_INPUT_ERR_MSG) 
    
    # Get the count of the original DataFrame
    input_df_count = df_to_process.count()
    # Prepare the source data by filtering for only one unique record
    df_to_process = prepare_source_data(input_df=df_to_process,
                                        unique_columns=unique_columns,
                                        timestamp_column=source_timestamp_column)
    
    data_manager_logger.info(LC.UPSERT_UNIQUE_TO_DELTA_MANAGED_PRE_FILTER_INFO_MSG.format(
        delta_table_path=delta_table_path, record_count=input_df_count)
    )

    merge_condition = ' AND '.join(
            f"delta_table.{col_name} = df_to_process.{col_name}" for col_name in unique_columns)

    # Define the update condition to ensure only the latest records are retained
    update_condition = f"delta_table.{source_timestamp_column} < df_to_process.{source_timestamp_column}"
    
    # Define the insert condition to ensure only rows with a source_timestamp_column are inserted
    insert_condition = f"df_to_process.{source_timestamp_column} is not null"
    
    # Get the list of columns to update, excluding msftCreatedDateTime during updates
    update_columns = [col for col in df_to_process_columns if col != GC.DEFAULT_SILVER_FHIR_TABLE_MSFT_CREATED_DATE_COL]
    update_set = {col: f"df_to_process.{col}" for col in update_columns}
    
    # Perform the merge operation
    delta_table.alias("delta_table").merge(
            source=df_to_process.alias("df_to_process"), condition=merge_condition
        ).whenMatchedUpdate(
            condition=update_condition,
            set=update_set
        ).whenNotMatchedInsertAll(condition=insert_condition
        ).execute()
        
    records_info = get_num_records_delta_op(delta_table_path=delta_table_path, spark_session=spark_session)
    
    # Get the number of filtered records
    filtered_record_count = input_df_count - records_info['num_source_rows']
    data_manager_logger.info(LC.UPSERT_UNIQUE_TO_DELTA_MANAGED_POST_FILTER_INFO_MSG.format(
        delta_table_path=delta_table_path, record_count=filtered_record_count)
    )
    
    # Log the number of records successfully persisted and filtered given the insert condition
    data_manager_logger.info(LC.UPSERT_UNIQUE_TO_DELTA_MANAGED_MERGED_INFO_MSG.format(
        delta_table_path=delta_table_path, 
        num_records_persisted=records_info['num_records_persisted'],
        num_records_filtered=records_info['num_records_filtered'],
        source_timestamp_column=source_timestamp_column,
        insert_condition=insert_condition,
        execution_time_ms=records_info['execution_time_ms'])
    )
    
    if collect_metrics_fn and callable(collect_metrics_fn):
        collect_metrics_fn(target_table_path=delta_table_path)

def update_unique_to_delta_managed(spark_session: SparkSession,
                                    data_manager_logger: DataManagerLogger,
                                    df_to_process: DataFrame,
                                    delta_table_path: str,
                                    unique_columns: List[str],
                                    **kwargs):
    """
    Update data from a source DataFrame into a Delta table based on unique columns. 
    The dataframe should only contain unique records
    
    Parameters:
    - spark_session: Active Spark session.
    - data_manager_logger: Logger for capturing logs.
    - df_to_process: Source DataFrame to be upserted.
    - delta_table_path: The path to the target delta table.
    - unique_columns: List of columns that define uniqueness for upsert.
    - delta_database: Optional database name where the Delta table resides.
    - kwargs: dict - An optional dictionary of keyword arguments 
            to pass to the upsert_unique_to_delta_managed:
                - source_modified_on_column: Timestamp column of when the source data was last modified. 
                Used to identify the latest version of the source data. Default is 'meta_lastUpdated'
                - collect_metrics_fn: Callable - A function to collect metrics for the operation

    Returns:
    None
    """
    
    collect_metrics_fn = kwargs.get("collect_metrics_fn", None)
    # Add the normalized msftModifiedDatetime and msftCreatedDatetime column with the current timestamp
    # we need to add it at the beginning of the process to ensure delta schema will have it
    df_to_process = add_normalized_current_timestamp_column(spark_session=spark_session,
                                                            input_df=df_to_process,
                                                            column_name=GC.DEFAULT_SILVER_MODIFIED_DATE_COL)
    
    df_to_process = add_normalized_current_timestamp_column(spark_session=spark_session,
                                                            input_df=df_to_process,
                                                            column_name=GC.DEFAULT_SILVER_FHIR_TABLE_MSFT_CREATED_DATE_COL)
    
    df_to_process_columns = df_to_process.columns
        
    # By default 'meta_lastUpdated' is the timestamp column for Silver tables
    source_timestamp_column = kwargs.get("source_modified_on_column", GC.DEFAULT_SOURCE_MODIFIED_ON_COLUMN)
    
    # Ensure msftModifiedDatetime is the first column for indexing
    if GC.DEFAULT_SILVER_MODIFIED_DATE_COL in df_to_process_columns:
        columns = [GC.DEFAULT_SILVER_MODIFIED_DATE_COL] + [col for col in df_to_process_columns if col != GC.DEFAULT_SILVER_MODIFIED_DATE_COL]
        df_to_process = df_to_process.select(columns)
    
    delta_table = get_or_create_managed_delta_table_using_path(spark_session=spark_session,
                                                        data_manager_logger=data_manager_logger,
                                                        df_to_process=df_to_process,
                                                        delta_table_path=delta_table_path
                                                        )
    # Check if DataFrame is empty
    if df_to_process.isEmpty():
        data_manager_logger.debug(LC.UPDATE_UNIQUE_TO_DELTA_MANAGED_SKIPPED.format(
            delta_table_path=delta_table_path)
        )
        return
    
    if not unique_columns:
        data_manager_logger.error(LC.EMPTY_UNIQUE_COLUMNS_INPUT_ERR_MSG)
        raise ValueError(LC.EMPTY_UNIQUE_COLUMNS_INPUT_ERR_MSG) 
    
    # Get the count of the original DataFrame
    input_df_count = df_to_process.count()
    # Prepare the source data by filtering for only one unique record
    df_to_process = prepare_source_data(input_df=df_to_process,
                                        unique_columns=unique_columns,
                                        timestamp_column=source_timestamp_column)
    
    data_manager_logger.info(LC.UPDATE_UNIQUE_TO_DELTA_MANAGED_PRE_FILTER_INFO_MSG.format(
        delta_table_path=delta_table_path, record_count=input_df_count)
    )

    merge_condition = ' AND '.join(
            f"delta_table.{col_name} = df_to_process.{col_name}" for col_name in unique_columns)

    # Define the update condition to ensure only the latest records are retained
    update_condition = f"delta_table.{source_timestamp_column} < df_to_process.{source_timestamp_column}"
    
    # Get the list of columns to update, excluding msftCreatedDateTime during updates
    update_columns = [col for col in df_to_process_columns if col != GC.DEFAULT_SILVER_FHIR_TABLE_MSFT_CREATED_DATE_COL]
    update_set = {col: f"df_to_process.{col}" for col in update_columns}
    
    # Perform the merge operation
    delta_table.alias("delta_table").merge(
            source=df_to_process.alias("df_to_process"), condition=merge_condition
        ).whenMatchedUpdate(
            condition=update_condition,
            set=update_set
        ).execute()
        
    records_info = get_num_records_delta_op(delta_table_path=delta_table_path, spark_session=spark_session)
    
    # Get the number of filtered records
    filtered_record_count = input_df_count - records_info['num_source_rows']
    data_manager_logger.info(LC.UPDATE_UNIQUE_TO_DELTA_MANAGED_POST_FILTER_INFO_MSG.format(
        delta_table_path=delta_table_path, record_count=filtered_record_count)
    )
    
    # Log the number of records successfully persisted and filtered given the insert condition
    data_manager_logger.info(LC.UPDATE_UNIQUE_TO_DELTA_MANAGED_MERGED_INFO_MSG.format(
        delta_table_path=delta_table_path, 
        num_records_persisted=records_info['num_records_persisted'],
        num_records_filtered=records_info['num_records_filtered'],
        source_timestamp_column=source_timestamp_column,        
        execution_time_ms=records_info['execution_time_ms'])
    )
    
    if collect_metrics_fn and callable(collect_metrics_fn):
        collect_metrics_fn(target_table_path=delta_table_path)

def prepare_source_data(input_df: DataFrame,
                        unique_columns: Optional[List[str]] = None,
                        timestamp_column: str = GC.DEFAULT_SOURCE_MODIFIED_ON_COLUMN
                        ) -> DataFrame:
    """
    Prepares the source data by retaining only the latest records based on unique columns and non-null timestamps.

    This function creates a window partitioned by the unique columns and ordered by the timestamp column in descending order.
    It then assigns a row number to each row within its window partition and filters to keep only the first row (i.e., the latest record) in each window partition.
    The function also logs the number of filtered records.
    
    Parameters:
    - input_df: Source DataFrame.
    - unique_columns: List of columns that define uniqueness.
    - timestamp_column: Column name representing the timestamp. Default is "meta_lastUpdated".
    
    Returns:
    DataFrame with only the latest records.
    """
    
    # Ensure df is a DataFrame
    if not isinstance(input_df, DataFrame):
        raise ValueError(LC.UPSERT_UNIQUE_TO_DELTA_MANAGED_ERR_MSG)
    
    if unique_columns is None:
        unique_columns = GC.DEFAULT_SILVER_UNIQUE_COLUMNS

    # Define a window partitioned by the unique columns, ordered by the timestamp column in descending order
    window = Window.partitionBy(*unique_columns).orderBy(desc(timestamp_column))

    # Filter to keep only the first row (i.e., the latest record) in each window partition
    df_latest = input_df.withColumn("row_num", row_number().over(window)).\
        filter(col("row_num") == 1).drop("row_num")
    
    return df_latest

def append_to_delta_table_using_path(
    df_to_process: DataFrame,
    delta_table_path: str,
    logger:DataManagerLogger,
    partition_cols: Optional[List[str]] = None,
    **kwargs
):
    """
    Write the dataframe to delta_table_path.
    Merges schema if dataframe schema is different from the table in the path.

    Arguments:
    - df_to_process : DataFrame - dataframe to save
    - delta_table_path: the path to the delta table
    - logger - DataManagerLogger to use
    - partition_cols: List[str] - list of columns to partition by
    - kwargs: dict - An optional dictionary of keyword arguments
        - collect_metrics_fn: Callable - A function to collect metrics for the operation
    """
    collect_metrics_fn = kwargs.get("collect_metrics_fn", None)
    if df_to_process is not None:
        df_to_process = add_current_timestamp_column(input_df=df_to_process, column_name=GC.DEFAULT_BRONZE_CREATED_DATE_COL)

    logger.info(f'{LC.SAVE_DELTA_TABLE_TO_PATH_INFO_MSG.format(table_path=delta_table_path)}')
    df_writer = df_to_process.write.option("mergeSchema", "true").mode("append").format("delta")
    
    if partition_cols:
        df_writer = df_writer.partitionBy(partition_cols)
    
    df_writer.save(delta_table_path)
    
    if collect_metrics_fn and callable(collect_metrics_fn): 
        collect_metrics_fn(target_table_path=delta_table_path)
        
def get_num_records_delta_op(delta_table_path: str, spark_session: SparkSession):
    """
    Get the number of records that were modified (merged, updated, or inserted) and not modified in the most recent operation on a Delta table. 
    This method is more effecient as it uses the DeltaTable.history method to get the most recent operation metrics compared to using Dataframe 
    count API that would need to scan the whole data to get the count.

    Parameters:
    - delta_table_path: The path to the Delta table.
    - spark: The SparkSession object.

    Returns:
    A dictionary containing the number of records persisted and the number of records filtered before persisting in the most recent operation.
    """
    # Create a DeltaTable object
    delta_table = find_managed_delta_table_using_path(spark_session=spark_session,
                                               delta_table_path=delta_table_path)

    if not delta_table:
        raise ValueError(f"Delta table not found at path: {delta_table_path}")
    
    # Retrieve the full Delta table history
    history_df = delta_table.history()

    # Filter the history to include only "MERGE" or "WRITE" operations
    filtered_history = history_df.filter(F.col("operation").isin("MERGE", "WRITE"))

    # Order by timestamp in descending order and get the most recent operation
    latest_op_df = filtered_history.orderBy(F.col("timestamp").desc()).limit(1)
    last_op = {}
    
    if latest_op_df.count() > 0:
        last_op = latest_op_df.collect()[0].asDict(recursive=True)
    
    # Get the operation metrics for the most recent operation
    operation = last_op.get("operation", "")
    operation_metrics: dict = last_op.get("operationMetrics", {})
    operation_parameters: dict = last_op.get("operationParameters", {})

    # Initialize the number of records persisted to 0
    num_records_persisted = 0
    
    # Initialize the number of records modified to 0
    num_records_modified = 0
    
    # Initialize number of targetFilesAdded to 0
    num_target_files = 0

    # If the operation was a merge, add the number of inserted and updated records
    if operation == "MERGE":
        num_records_persisted = int(operation_metrics.get("numTargetRowsInserted", "0"))
        num_records_modified += num_records_persisted
        num_records_modified += int(operation_metrics.get("numTargetRowsUpdated", "0"))
        num_target_files = int(operation_metrics.get("numTargetFilesAdded", "0"))
        
    # If the operation was a write, add the number of output rows
    elif operation == "WRITE":
        num_target_files = int(operation_metrics.get("numFiles", "0"))
        num_records_persisted = int(operation_metrics.get("numOutputRows", "0"))

    # Get the total number of source rows processed
    num_source_rows = int(operation_metrics.get("numSourceRows", "0"))

    # Calculate the number of records not modified
    num_records_filtered = num_source_rows - num_records_modified

    # Ensure that num_records_filtered is not less than zero
    num_records_filtered = max(0, num_records_filtered)

    # Return a dictionary with the num_records_persisted and num_records_filtered
    return {
        'num_records_persisted': num_records_persisted,
        'num_records_filtered': num_records_filtered,
        'num_source_rows': num_source_rows,
        'num_target_files': num_target_files,
        'num_output_bytes': int(operation_metrics.get("numOutputBytes", 0)),
        'num_records_inserted': int(operation_metrics.get("numTargetRowsInserted", 0)),
        'num_records_updated': int(operation_metrics.get("numTargetRowsUpdated", 0)),
        'execution_time_ms': int(operation_metrics.get("executionTimeMs", 0)),
        'operation': operation,
        'operation_mode': operation_parameters.get("mode", "Unknown"),
        'operation_timestamp': last_op.get("timestamp")
    }
    
def update_or_extract_namespace(df: DataFrame, target_column: str, file_path_column: str) -> DataFrame:
    """
    Updates the target column with the namespace extracted from the file path column if the extracted namespace is not empty.

    This function checks each row of the specified target column in the DataFrame. If the target column is empty for a row,
    it extracts the namespace from the file path column based on a predefined pattern and updates the target column with this value.
    The namespace is extracted following the pattern 'External/[Modality]/[DataFormat]/[Namespace]' or 'Process/[Modality]/[DataFormat]/[Namespace]' from the file path.

    Args:
        df (DataFrame): The DataFrame to process.
        target_column (str): The name of the column to update with the extracted namespace.
        file_path_column (str): The name of the column containing the file path from which to extract the namespace.

    Returns:
        DataFrame: The updated DataFrame with the target column updated based on the file path column.
    """
    # This pattern captures the namespace after 'External/[Modality]/[DataFormat]/[Namespace]' or 'Process/[Modality]/[DataFormat]/[Namespace]'
    pattern = r".*/(External|Process)/[^/]+/[^/]+/([^/]+)/.*"
    
    extracted_namespace_expr = regexp_extract(col(file_path_column), pattern, 2)
    return df.withColumn(
        target_column,
        when(
            (extracted_namespace_expr != ''),
            extracted_namespace_expr
        ).otherwise(lit(None))
    )

def validate_checkpoint(spark: SparkSession, logger: DataManagerLogger, target_table_path: str, checkpoint_path: str,  mssparkutils_client: MSSparkUtilsClientBase, resource_name: str = "") -> None:
    """
    Validate the checkpoint path before streaming. Remove the checkpoint metadata when conditions are met.
    
    Args:
        spark (SparkSession): The active Spark session.
        logger (DataManagerLogger): Logger to log messages.
        target_table_path (str): The target table path.
        checkpoint_path (str): The checkpoint path.
    """
    
    def delta_table_has_checkpoint(checkpoint_path: str, mssparkutils_client: MSSparkUtilsClientBase) -> bool:
        """
        Check if the Delta table has a checkpoint.

        Args:
            checkpoint_path (str): The checkpoint path.

        Returns:
            bool: True if the checkpoint exists, False otherwise.
        """
        return mssparkutils_client.fs_exists(checkpoint_path)

    def remove_checkpoint_metadata(checkpoint_path: str, mssparkutils_client: MSSparkUtilsClientBase, logger: DataManagerLogger) -> None:
        """
        Remove the checkpoint metadata.

        Args:
            checkpoint_path (str): The checkpoint path.
            logger (DataManagerLogger): Logger to log messages.
        """
        try:
            mssparkutils_client.fs_rm(checkpoint_path, recursive=True)
            logger.info(f"Checkpoint metadata at {checkpoint_path} removed successfully.")
        except Exception as e:
            logger.error(f"Failed to remove checkpoint metadata at {checkpoint_path}. Error: {str(e)}")
            
    def is_delta_table_empty(spark: SparkSession, delta_table_path: str, logger: DataManagerLogger) -> bool:
        """
        Check if the Delta table is empty.

        Args:
            spark (SparkSession): The active Spark session.
            delta_table_path (str): The path to the Delta table.
            logger (DataManagerLogger): Logger to log messages.

        Returns:
            bool: True if the Delta table is empty, False otherwise.
        """
        
        try:
            delta_table = DeltaTable.forPath(spark, delta_table_path)
            table_details_df = delta_table.detail()
            
            # Use DataFrame operations to check if the table is empty
            is_empty = table_details_df.filter((col("numFiles") == 0) & (col("sizeInBytes") == 0)).count() > 0
            
            return is_empty
        except Exception as e:
            logger.error(LC.GENERIC_DELTA_TABLE_EMPTY_CHECK_ERROR_MSG.format(error_message=str(e)))
            return False
        
    try:
        if resource_name == "":
            resource_name = target_table_path.split("/")[-1]
            
        if not DeltaTable.isDeltaTable(spark, target_table_path) and delta_table_has_checkpoint(checkpoint_path, mssparkutils_client):
            logger.info(LC.GENERIC_VALIDATE_CHECKPOINT_NO_DELTA_TABLE_MSG.format(resource_name=resource_name))
            remove_checkpoint_metadata(checkpoint_path, mssparkutils_client, logger)
        
        if DeltaTable.isDeltaTable(spark, target_table_path) and is_delta_table_empty(spark, target_table_path, logger) and delta_table_has_checkpoint(checkpoint_path, mssparkutils_client):
            logger.info(LC.GENERIC_VALIDATE_CHECKPOINT_NO_DATA_MSG.format(resource_name=resource_name))
            remove_checkpoint_metadata(checkpoint_path, mssparkutils_client, logger)
    
    except Exception as e:
        logger.error(f"Failed to validate checkpoint. Error: {str(e)}")
        error_message = LC.GENERIC_VALIDATE_CHECKPOINT_FAILED_ERROR_MSG.format(resource_name=resource_name)
        logger.error(error_message)

def delete_record(spark: SparkSession, delta_table_path: str, table_name: str, record_id: str, logger: DataManagerLogger) -> None:
    """
    Delete a record from the specified Delta table using the DataFrame API.

    Parameters:
    - spark: The active Spark session.
    - delta_table_path: The path to the Delta table.
    - table_name: The name of the table from which to delete the record.
    - record_id: The unique identifier of the record to delete.
    - logger: Logger to log messages.
    """
    # Validate inputs
    if not table_name or not record_id:
        logger.error("Table name and record ID must be provided.")
        raise ValueError("Table name and record ID must be provided.")

    try:
        # Construct the full path to the Delta table
        table_path = f"{delta_table_path}/{table_name}"
        
        # Load the Delta table
        delta_table = DeltaTable.forPath(spark, table_path)

        # Perform the delete operation
        delta_table.delete(condition=f"id = '{record_id}'")
        
        # Log success message
        logger.info(f"Record with ID '{record_id}' deleted from '{table_name}'.")
    except Exception as e:
        # Log error message
        logger.error(f"Failed to delete record with ID '{record_id}' from '{table_name}': {e}")

def get_record(spark: SparkSession, column_name: str, record_id: int, delta_table_path: str, table_name: str, model_class: Any, logger: DataManagerLogger) -> Optional[Any]:
    """
    Retrieve information based on the record ID.

    Args:
        spark (SparkSession): The active Spark session.
        column_name (str): The name of the column to filter by.
        record_id (int): The ID of the record.
        delta_table_path (str): The path to the Delta table.
        table_name (str): The name of the table.
        model_class (Any): The class of the model.
        logger (DataManagerLogger): Logger to log messages.

    Returns:
        Optional[Any]: The information of the record, or None if not found.
    """
    try:
        # Construct the full path to the Delta table
        full_delta_table_path = f"{delta_table_path}/{table_name}"
        # Load the Delta table
        delta_table = DeltaTable.forPath(spark, full_delta_table_path)
        
        # Use the DeltaTable API to filter records
        result_df = delta_table.toDF().filter(col(column_name) == record_id)
        
        # Collect the results
        result = result_df.collect()
        
        if result:
            return model_class(**result[0].asDict())
        
    except Exception as e:
        logger.error(f"Failed to retrieve record with ID '{record_id}' from '{table_name}': {e}")
    
    return None

def get_active_records(
    spark: SparkSession,
    column_name: str,
    record_id_list: set,
    delta_table_path: str,
    table_name: str,
    logger: DataManagerLogger
) -> set:
    """
    Retrieve recent records based on a list of record IDs.

    Args:
        spark (SparkSession): The active Spark session.
        column_name (str): The name of the column to filter by.
        record_id_list (List[str]): The list of record IDs.
        delta_table_path (str): The path to the Delta table.
        table_name (str): The name of the table.
        logger (DataManagerLogger): Logger to log messages.

    Returns:
        List[str]: The list of record IDs that exist in the Delta table.
    """
    try:
        full_delta_table_path = f"{delta_table_path}/{table_name}"

        # Load the Delta table and filter records based on a list of record_id values
        existing_ids_df = DeltaTable.forPath(spark, full_delta_table_path).toDF().filter(
            col(column_name).isin(record_id_list)
        ).select(column_name)

        existing_data = {row[column_name] for row in existing_ids_df.collect()}
        return existing_data
    except Exception as e:
        logger.error(f"Failed to retrieve records in '{table_name}': {e}")
        return []

