from pyspark.sql import SparkSession, DataFrame
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.medical_imaging.dicom.core.constants import ImagingStudyConstants as C
from microsoft.fabric.hls.hds.utils.logging_helper import LoggingHelper
from microsoft.fabric.hls.hds.utils.utils import Utils as CommonUtils
from microsoft.fabric.hls.hds.utils.utils import FolderPath
from microsoft.fabric.hls.hds.utils.data_manager_logger import DataManagerLogger
from microsoft.fabric.hls.hds.structured_stream.delta_table_stream_reader import DeltaTableStreamReader
from pyspark.sql.types import *
from pyspark.sql.functions import *
from microsoft.fabric.hls.hds.utils.parameter_service import ParameterService
from microsoft.fabric.hls.hds.utils.business_events_ingestion_handler import BusinessEventsIngestion
import uuid

class BaseCustomTableCreator:
    """
    Class used to create custom tables in the target lakehouse. This class is meant to be inherited by the modalities custom table creator classes.
    """ 
    
    def __init__(self, 
                spark: SparkSession,
                workspace_name: str,
                solution_name: str,
                one_lake_endpoint: str,
                parameter_service: ParameterService,
                business_events_ingestion_service: BusinessEventsIngestion,
                collect_metrics_fn,
                logger: DataManagerLogger) -> None:
        """
        Args:
            - spark: spark session
            - workspace_name: Name of the Fabric Workspace
            - solution_name (str): Name of the HDS-Healthcare data solutions OneLake workload solution
            - one_lake_endpoint (str): The one lake endpoint
            - parameter_service (ParameterService): The parameter service object
            - business_events_ingestion_sevice (BusinessEventsIngestion): The business events ingestion service instance.
            - collect_metrics_fn : collects the target table operation summary metrics
            - logger (DataManagerLogger): The logger instance            
        """
        try:
            self.spark: SparkSession = spark
            self.workspace_name = workspace_name
            self.solution_name = solution_name
            self.parameter_service = parameter_service
            self.one_lake_endpoint = one_lake_endpoint
            self.business_events_ingestion_service = business_events_ingestion_service
            self.target_lakehouse_name = self.parameter_service.get_foundation_config_value(GC.SILVER_LAKEHOUSE_ID_KEY)
            self.source_lakehouse_name = self.parameter_service.get_foundation_config_value(GC.BRONZE_LAKEHOUSE_ID_KEY)

            self.pipeline_run_id = self.parameter_service.get_foundation_config_value(GC.PIPELINE_RUN_ID_KEY)
            self.config_files_root_path = FolderPath.get_fabric_workload_files_root_path(workspace_name=self.workspace_name,
                                                                                one_lake_endpoint=self.one_lake_endpoint,
                                                                                solution_name=self.solution_name)
            self.checkpoint_path_prefix = self.parameter_service.get_activity_config_value(
                GC.CHECKPOINT_PATH_KEY,
                FolderPath.get_fabric_workload_files_checkpoint_folder_path(root_path=self.config_files_root_path,
                                                                            checkpoint_folder_name=self.target_lakehouse_name),
            )        
            self.max_files_per_trigger = self.parameter_service.get_activity_config_value(
                GC.MAX_FILES_PER_TRIGGER_KEY,
                GC.DEFAULT_NUMBER_OF_FILES_PER_TRIGGER_SILVER,
                "int"  
            )
            self.max_bytes_per_trigger = self.parameter_service.get_activity_config_value(
                GC.MAX_BYTES_PER_TRIGGER_KEY,
                GC.DEFAULT_NUMBER_OF_BYTES_PER_TRIGGER_SILVER,
                "int"
            )
            self.collect_metrics_fn = collect_metrics_fn
            self._logger = logger

            self.target_table_path = self.parameter_service.get_activity_config_value(
                GC.TARGET_TABLES_PATH_KEY,
                FolderPath.get_fabric_tables_path(
                    workspace_name=self.workspace_name,
                    one_lake_endpoint=self.one_lake_endpoint,
                    lakehouse_name=self.target_lakehouse_name
                ),
            )
            self.source_table_path = self.parameter_service.get_activity_config_value(
                GC.SOURCE_TABLES_PATH_KEY,
                FolderPath.get_fabric_tables_path(
                    workspace_name=self.workspace_name,
                    one_lake_endpoint=self.one_lake_endpoint,
                    lakehouse_name=self.source_lakehouse_name
                )
            )
        except Exception as ex:
            self._logger.error(message=str(ex))
            
            # Insert a row into Business Events table
            be_row = self.business_events_ingestion_service.create_new_business_event_row(
                id =str(uuid.uuid4())
                , activityName =    GC.BASE_CUSTOM_TABLE_CREATOR_SERVICE
                , sourceLakehouseName= f"{self.source_lakehouse_name}"
                , targetLakehouseName= f"{self.target_lakehouse_name}" 
                , runId =           self.pipeline_run_id
                , severity =        GC.ERROR
                , eventType=        GC.BE_EVENT_INIT_FAILED
                , message=          str(ex)   
                , exception=        str(ex)                
            )
            self.business_events_ingestion_service.insert_business_events([be_row])
            
            raise
        
    def transform_data(self, df: DataFrame, epoch_id: str):
        """
        This method is used to transform the data to the target lakehouse. It must be implemented by the child class.
        """
        pass

    def read_stream(self, source_table_path):
        """
        This method is used to set up the structured streaming from the source.

        Args:
            source_table_path: The path to the source table          

        """
        try:
            stream_reader = DeltaTableStreamReader(
                                self.spark,
                                maxFilesPerTrigger= self.max_files_per_trigger,
                                maxBytesPerTrigger= self.max_bytes_per_trigger)
            return stream_reader.set_up_streaming(
                    source_table_path    
                    )
        except Exception as e:
            self._logger.error(
                LC.SPARK_CUSTOM_STREAM_READ_ERR_MSG.format(
                    table_path = self.source_table_path,
                    error_msg = str(e)
                )
            )
            
            # Insert a row into Business Events table
            be_row = self.business_events_ingestion_service.create_new_business_event_row(
                id =str(uuid.uuid4())
                , activityName =    GC.BASE_CUSTOM_TABLE_CREATOR_SERVICE
                , sourceLakehouseName= f"{self.source_lakehouse_name}"
                , targetLakehouseName= f"{self.target_lakehouse_name}" 
                , runId =           self.pipeline_run_id
                , severity =        GC.ERROR
                , eventType=        GC.BE_EVENT_READ_STREAM_FAILED
                , message=          str(e)   
                , exception=        str(e)                
            )
            self.business_events_ingestion_service.insert_business_events([be_row])
            
            raise            
        
    def pre_process_read_data(self, df:DataFrame) -> DataFrame:
        """
        This method is used to process the dataframe read from the source table.

        Args:
            df (DataFrame): The DataFrame containing the data from the source table.            

        Returns:
            DataFrame: The processed DataFrame.
        """
        pass

    def write_stream(self, df:DataFrame, checkpoint_path):
        """
        This method is used to write the dataframe to the target table path.

        Args:
            df (DataFrame): The DataFrame containing the source table data.            
        """
        try:
            self.spark.sparkContext.setJobGroup(f"{self.__class__.__module__}.{self.__class__.__qualname__}", f"Writing dataframe to target table path with checkpoint path: {checkpoint_path}" )
            query = (df.writeStream.format("delta")
                        .trigger(availableNow=True)
                        .option("checkpointLocation", checkpoint_path)
                        .foreachBatch(self.transform_data)
                        .start())
            query.awaitTermination()
        except Exception as e:
            self._logger.error(
                LC.SAVING_RESOURCE_ERR_MSG.format(
                    table_path = self.target_table_path,
                    error_msg = str(e)
                )
            )
            
            # Insert a row into Business Events table
            be_row = self.business_events_ingestion_service.create_new_business_event_row(
                id =str(uuid.uuid4())
                , activityName =    GC.BASE_CUSTOM_TABLE_CREATOR_SERVICE
                , sourceLakehouseName= f"{self.source_lakehouse_name}"
                , targetLakehouseName= f"{self.target_lakehouse_name}" 
                , runId =           self.pipeline_run_id
                , severity =        GC.ERROR
                , eventType=        GC.BE_EVENT_WRITE_STREAM_FAILED
                , message=          str(e)   
                , exception=        str(e)                
            )
            self.business_events_ingestion_service.insert_business_events([be_row])
            
            raise    

    def process(self):
        """
        This method is used to initiate the processing for custom table transformation from source to target lakehouse. It must be implemented by the child class.

        """
        pass
