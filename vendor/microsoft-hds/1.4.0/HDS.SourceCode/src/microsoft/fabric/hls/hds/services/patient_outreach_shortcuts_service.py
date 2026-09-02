# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
import concurrent.futures
from typing import Dict, Callable
from delta import DeltaTable
from pyspark.sql import SparkSession, DataFrame
from microsoft.fabric.hls.hds.errors.silver_ingestion_failed_error import SilverIngestionFailedError
from microsoft.fabric.hls.hds.utils.dataframe_utils import is_delta_table_empty, find_managed_delta_table_using_path, has_schema_evolved
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants
from microsoft.fabric.hls.hds.utils.logging_helper import LoggingHelper
from microsoft.fabric.hls.hds.utils.shortcut_manager import ShortcutsManager
from microsoft.fabric.hls.hds.utils.utils import FolderPath, Utils


class PatientOutReachShortcutsService:
    def __init__(self, 
                 spark: SparkSession,
                 workspace_name: str,
                 **kwargs):
        """
        Initialize the PatientOutReachShortcutsService class.

        Args:
            - spark (SparkSession): The Spark session.
            - workspace_name (str): The name of the workspace.
            - **kwargs (dict): An optional dictionary that customer can use to configure the patient outreach shortcuts service
                - run_id (str): The run_id for the run. If none is provided, one will be generated
        """
        self.spark = spark
        self.workspace_name = workspace_name
        self.bronze_lakehouse_name = kwargs.get("bronze_lakehouse_name", GlobalConstants.DEFAULT_BRONZE_LAKEHOUSE_NAME)
        self.one_lake_endpoint = kwargs.get("one_lake_endpoint", GlobalConstants.DEFAULT_ONE_LAKE_ENDPOINT)
        self.shortcuts_manager = ShortcutsManager(self.spark)
        self._logger = LoggingHelper.get_patientoutreach_shortcuts_creation_logger(
                self.spark, self.__class__.__name__, GlobalConstants.LOGGING_LEVEL
            )

    def create_cds_shortcut_tables(self, cds_lakehouse_name: str, cds_tables, dv_schema: str):
        """
        Create the CDS shortcut tables.

        Args:
            cds_lakehouse_name (str): The name of the CDS lakehouse.
            cds_tables (list): The list of Required CDS tables.
            dv_schema (str): The DV schema.
        """
        self._logger.info(f"{LoggingConstants.POA_CREATE_CDS_SHORTCUT_TABLES_START_INFO_MSG}")
        source_lake_path = FolderPath.get_fabric_tables_path(self.workspace_name, self.one_lake_endpoint, cds_lakehouse_name)
        cds_tables_list = [t.name for t in self.spark.catalog.listTables(cds_lakehouse_name)]
        cds_shortcuts = [table for table in cds_tables if table in cds_tables_list]
        for table in cds_shortcuts:
            try:
                self.shortcuts_manager.create_shortcut_table(self.bronze_lakehouse_name,table,f"{dv_schema}_{table}", source_lake_path, self._logger)
            except Exception as e:
                self._logger.error(f"{self.bronze_lakehouse_name}`.`{dv_schema}_{table}`:", e)
        self._logger.info(f"{LoggingConstants.POA_CREATE_CDS_SHORTCUT_TABLES_COMPLETED_INFO_MSG}")

    def create_marketing_analytics_shortcut_tables(self, mkt_analytics_lakehouse_name: str, mkt_schema: str):
        """
        Create the marketing analytics shortcut tables.

        Args:
            mkt_analytics_lakehouse_name (str): The name of the marketing analytics lakehouse.
            mkt_schema (str): The marketing schema.
        """
        self._logger.info(f"{LoggingConstants.POA_CREATE_MARKETING_ANALYSIS_SHORTCUT_TABLES_START_INFO_MSG}")
        source_lake_path = FolderPath.get_fabric_tables_path(self.workspace_name, self.one_lake_endpoint, mkt_analytics_lakehouse_name)
        mkt_tables = self.spark.catalog.listTables(mkt_analytics_lakehouse_name)
        for table in mkt_tables:
            try:
                self.shortcuts_manager.create_shortcut_table(self.bronze_lakehouse_name,table.name,f"{mkt_schema}_{table.name}", source_lake_path, self._logger)
            except Exception as e:
                self._logger.error(f"{self.bronze_lakehouse_name}`.`{mkt_schema}_{table.name}`:", e)
        self._logger.info(f"{LoggingConstants.POA_CREATE_MARKETING_ANALYSIS_SHORTCUT_TABLES_COMPLETED_INFO_MSG}")