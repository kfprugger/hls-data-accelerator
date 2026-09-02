"""This module contains the class and methods to execute the sql scripts for idp deployment.
"""
from typing import Dict
from pyspark.sql import SparkSession
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants
from microsoft.fabric.hls.hds.utils.logging_helper import LoggingHelper


class DDLHelper:
    """This class contains methods for executing the spark sql ddl scripts.
    """

    def __init__(self,
                 spark_session: SparkSession,
                 sql_script_path: str,
                 placeholder_values: Dict):
        """
        Initialize the DDL helper class.

        Args:
            spark_session (SparkSession):
                The SparkSession object to be used for all data processing.
            sql_script_path (str):
                The base path/folder on the storage account where the omop scripts are located.
            placeholder_values (Dict): The placeholder parameter values to be replaced
                        in the script file before executing it.
                        E.g: {
                            '@omopDatabaseSchema': 'omop_db',
                            '@omopStoragePath': 'abfss://silver@idpstoragedev.xyz.net/omop_db/
                        }.
        """
        self.spark_session = spark_session
        self._logger = LoggingHelper.get_generic_logger(
            self.spark_session, self.__class__.__name__, GlobalConstants.LOGGING_LEVEL)
        self._omop_sql_script_path = sql_script_path
        self._placeholder_values = placeholder_values

    def execute_ddl_script(
        self,
        file_name: str
    ):
        """Reads a sql script file from storage container and executes the script statements.
            Expects the sql statements separated by the semicolon character.
            Arguments:
                file_name: The name of the sql script file on the storage container/folder.

        """

        # Read script
        script_text = self.spark_session.read.text(
            self._omop_sql_script_path + file_name, wholetext=True).collect()[0][0]
        for placeholder in self._placeholder_values:
            script_text = script_text.replace(
                placeholder, self._placeholder_values[placeholder])

        # Execute ddl statements
        ddl_statements = script_text.split(';')
        for ddl_statement in ddl_statements:
            ddl_statement = ddl_statement.strip()
            if ddl_statement:
                # log the sql statement to azure analytics.
                self._logger.info(ddl_statement)
                # execute the sql statement.
                self.spark_session.sql(ddl_statement)
