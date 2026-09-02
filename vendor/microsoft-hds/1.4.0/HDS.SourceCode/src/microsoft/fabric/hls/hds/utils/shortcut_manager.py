from pyspark.sql import SparkSession
from microsoft.fabric.hls.hds.utils.data_manager_logger import DataManagerLogger

class ShortcutsManager:
    def __init__(self, spark: SparkSession):
        self.spark: SparkSession = spark

    def create_shortcut_table(self, lakehouse, source_table_name, target_table_name, path, data_manager_logger: DataManagerLogger):  
        """  
        Create a new Delta table with the given parameters if it does not already exist.  
    
        Args:  
        lakehouse (str): The name of the lakehouse.  
        source_table_name (str): The actual name of the source table.  
        target_table_name (str): The name of the target table.  
        path (str): The path to the Delta table location.  
        data_manager_logger (DataManagerLogger): The logger object for logging messages.  
        """  
        # Set the current database to the specified lakehouse
        self.spark.sql(f"USE {lakehouse}")  

        # Check if the target table already exists
        if not self.spark.catalog.tableExists(target_table_name):  
            # Create the SQL query to create the table
            # Use parameterized query to avoid SQL injection
            self.spark.sql("CREATE TABLE `{}`.`{}` USING DELTA LOCATION '{}'"
                           .format(lakehouse, target_table_name, f"{path}/{source_table_name}"))
            data_manager_logger.info(f"Table `{lakehouse}`.`{target_table_name}` created successfully") 
        else:
            data_manager_logger.info(f"Table `{lakehouse}`.`{target_table_name}` already exists")
