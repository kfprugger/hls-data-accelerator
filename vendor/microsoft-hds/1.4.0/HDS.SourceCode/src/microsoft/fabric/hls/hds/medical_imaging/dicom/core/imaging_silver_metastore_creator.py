# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
"""
Module with a class to create silver imaging metastore
"""
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.types import *
from pyspark.sql.functions import *
import json, uuid
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.utils.logging_helper import LoggingHelper
from microsoft.fabric.hls.hds.medical_imaging.dicom.core.constants import ImagingStudyConstants as C
from datetime import datetime
from microsoft.fabric.hls.hds.utils.base_custom_table_creator import BaseCustomTableCreator
from microsoft.fabric.hls.hds.utils.dataframe_utils import upsert_unique_to_delta_managed
from microsoft.fabric.hls.hds.flatten.normalization.normalization_manager import FlattenNormalization
from microsoft.fabric.hls.hds.utils.business_events_ingestion_handler import BusinessEventsIngestion
from microsoft.fabric.hls.hds.utils.parameter_service import ParameterService


class ImagingSilverMetaStoreCreator(BaseCustomTableCreator) :
    def __init__(self, 
                spark: SparkSession,
                workspace_name: str,
                solution_name: str,
                one_lake_endpoint: str,
                parameter_service: ParameterService,
                collect_metrics_fn) -> None:
        """
        Args:
            - spark (SparkSession): spark session
            - workspace_name (str): Name of the Fabric Workspace
            - solution_name (str): Name of the HDS-Healthcare data solutions OneLake workload solution
            - one_lake_endpoint (str): The one lake endpoint
            - parameter_service (ParameterService): The parameter service object
            - collect_metrics_fn : collects the target table operation summary metrics
        """
        self._logger = LoggingHelper.get_silver_custom_ingestion_logger(
            spark, self.__class__.__name__, GC.LOGGING_LEVEL)
        
        self.pipeline_run_id = parameter_service.get_foundation_config_value(GC.PIPELINE_RUN_ID_KEY)

        self.business_events_ingestion_service = BusinessEventsIngestion(
            spark = spark,
            workspace_name = workspace_name,
            one_lake_endpoint = one_lake_endpoint,
            lakehouse_name = parameter_service.admin_lakehouse_name,
            solution_name = solution_name,
            parameter_service = parameter_service
        )  
        super().__init__(spark=spark,
                        workspace_name=workspace_name,
                        solution_name=solution_name,
                        one_lake_endpoint=one_lake_endpoint,
                        parameter_service=parameter_service,
                        business_events_ingestion_service=self.business_events_ingestion_service,
                        collect_metrics_fn=collect_metrics_fn,
                        logger=self._logger)
        
        self.config_file_path =  f"{self.config_files_root_path}/{GC.DEFAULT_DICOM_CONFIGS_PATH}/{C.DICOM_TO_FHIR_MAPPING_FILE_NAME}"
        self.mapping_config = json.loads(
            self.spark.sparkContext.wholeTextFiles(
                self.config_file_path
            ).collect()[0][1]
        )

    def pre_process_read_data(self, df)-> DataFrame:
        """
        This method is used to process the dataframe read from the source table.

        Args:
            df (DataFrame): The DataFrame containing the data from the source table.            

        Returns:
            DataFrame: The prcessed DataFrame.
        """
        df = df[C.IMAGING_META_STORE_COLUMNS]
        
        # Read expression string ("calc") for field "id" from config mappings
        expr_str = ""
        if C.ID_COLUMN_NAME in self.mapping_config and C.CALC_FIELD in self.mapping_config[C.ID_COLUMN_NAME]:
            expr_str = f"{self.mapping_config[C.ID_COLUMN_NAME][C.CALC_FIELD]}"
        else:
            self._logger.error(
                LC.CONFIG_MAPPING_ERROR_MSG.format(
                    config_file_path=self.config_file_path
                )
            )
            raise KeyError(LC.CONFIG_MAPPING_ERROR_MSG.format(
                config_file_path=self.config_file_path
            ))
        
        # Creating udf for normalize_resource_id() function for datatype compatibility. normalize_resource_id() accepts source_system as Union[str, None] instead of type column.
        df = df.withColumn(C.ID_COLUMN_NAME,  udf(
                lambda orig_id, source_system: FlattenNormalization.normalize_resource_id(f"{orig_id}", C.FHIR_IMAGING_STUDY_RES_NAME, f"{source_system}"),
                StringType()
            )(
                eval(expr_str).cast(StringType()),
                col(C.SOURCE_SYSTEM_COLUMN_NAME)
            )
        )
        
        #renaming sourceSystem column to msftSourceSystem
        df = df.withColumnRenamed(C.SOURCE_SYSTEM_COLUMN_NAME, C.SILVER_SOURCE_SYSTEM_COLUMN_NAME) 
        return df    

    def transform_data(self, df: DataFrame, epoch_id: str):
        """
        This method is used to transform the data to the target lakehouse.

        """
        try:
            uniq_columns = C.IMAGING_META_STORE_UNIQUE_COLUMNS
            upsert_unique_to_delta_managed(spark_session=self.spark,
                                                    data_manager_logger=self._logger,
                                                    df_to_process=df,
                                                    unique_columns=uniq_columns,
                                                    delta_table_path=f"{self.target_table_path}/{C.IMAGING_META_STORE}",
                                                    source_modified_on_column=GC.DEFAULT_SILVER_MODIFIED_DATE_COL,
                                                    collect_metrics_fn =self.collect_metrics_fn
                                                    )
        except Exception as e:
            self._logger.error(
                LC.SAVING_RESOURCE_ERR_MSG.format(
                    table_path = self.target_table_path,
                    error_msg = str(e)
                )
            )
            
            # Insert a row into Business Events table
            be_upsert_failed = self.business_events_ingestion_service.create_new_business_event_row(
                id =str(uuid.uuid4())
                , activityName =    C.SILVER_IMAGING_METASTORE_SERVICE
                , sourceLakehouseName= f"{self.source_lakehouse_name}"
                , targetLakehouseName= f"{self.target_lakehouse_name}" 
                , sourceTableName= C.METADATA_TABLE_NAME
                , targetTableName= C.IMAGING_META_STORE
                , runId =           self.pipeline_run_id
                , severity =        GC.ERROR
                , eventType=        C.BE_EVENT_TYPE_MS_UPSERT_FAILED
                , message=          str(e)   
                , exception=        str(e)                
            )
            self.business_events_ingestion_service.insert_business_events([be_upsert_failed])
            
            raise

    def process(self):
        """
        This method is used to initiate the processing for custom table transformation from source to target lakehouse.

        """
        self._logger.info(LC.BEGAN_CUSTOM_TABLE_EXECUTION_INFO_MSG.format(source_table=C.METADATA_TABLE_NAME, 
            target_table=C.IMAGING_META_STORE,
            timestamp=datetime.now()))
        df = self.read_stream(f"{self.source_table_path}/{C.METADATA_TABLE_NAME}")
        if df is None:
            self._logger.info(message=LC.EMPTY_DATAFRAME)
            return
        df_filtered = self.pre_process_read_data(df)
        self.write_stream(df_filtered, f"{self.checkpoint_path_prefix}/{C.IMAGING_META_STORE}")
        self._logger.info(LC.COMPLETED_CUSTOM_TABLE_EXECUTION_INFO_MSG.format(source_table=C.METADATA_TABLE_NAME, 
            target_table=C.IMAGING_META_STORE,
            timestamp=datetime.now()))