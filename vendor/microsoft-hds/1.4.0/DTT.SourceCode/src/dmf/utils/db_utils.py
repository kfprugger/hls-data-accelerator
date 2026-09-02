from pathlib import Path

from pyspark.sql import SparkSession


def delete_table(spark: SparkSession, db: str, table: str, location: str):
    if not (spark or db or table or location):
        raise ValueError("Cannot delete table. Invalid input")

    spark.sql(f"drop table if exists {db}.{table}")
    _delete_files_from_table(spark, location)


def _delete_files_from_table(spark: SparkSession, location: str):
    file_system = spark.sparkContext._jvm.org.apache.hadoop.fs.FileSystem
    fs = file_system.get(spark.sparkContext._jsc.hadoopConfiguration())
    path = spark.sparkContext._jvm.org.apache.hadoop.fs.Path
    table_path = path(location)
    if fs.exists(table_path) and fs.isDirectory(table_path):
        fs.delete(table_path)


def create_table_like_another(spark: SparkSession,
                              source_table_db: str,
                              source_table_name: str,
                              new_table_db: str,
                              new_table_name: str,
                              new_table_location: Path):

    if not (spark or source_table_db or source_table_name or new_table_db or new_table_name or new_table_location):
        raise ValueError("Could not create table. Invalid input")

    create_table_sql = """
                CREATE TABLE IF NOT EXISTS {0}.{1}
                LIKE {2}.{3}
                USING PARQUET
                LOCATION '{4}'
            """.format(new_table_db, new_table_name, source_table_db, source_table_name, str(new_table_location))

    spark.sql(create_table_sql)
