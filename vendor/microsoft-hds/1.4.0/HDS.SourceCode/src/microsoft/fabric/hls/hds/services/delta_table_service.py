from pyspark.sql import SparkSession

class DeltaTableService:

    """
    Common utility functions for querying metastore and interacting with delta tables 
    """
    
    def __init__(self, spark: SparkSession):

        self.spark = spark

    def check_if_table_exists(self, database_name: str, list_of_tables: list) -> bool:
   
        """Given a list of tables, determine whether table exists in the data base

        Args:
         - database_name: The name of the database in which check the existence of tables 
         - list_of_tables: The table name to check if exists
        Returns:
            bool: True if the table exists in Database
        """
        db_tables = self.spark.catalog.listTables(database_name)
        list_of_table_names_in_catalog = [db_table.name.lower() for db_table in db_tables]
        return [
            item
            for item in list_of_tables
            if item.lower() not in list_of_table_names_in_catalog
        ]
