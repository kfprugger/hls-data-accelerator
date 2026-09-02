import logging
import uuid
from pyspark.sql.session import SparkSession
from microsoft.fabric.hls.hds.utils.data_manager_logger import DataManagerLogger
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC


class LoggingHelper:
    """
    Class to generate named instances of the DataManagerLogger
    """

    run_id = None

    @staticmethod
    def get_imaging_metadata_extraction_logger(
        spark: SparkSession,
        logger_name: str,
        log_level: int = logging.DEBUG,
        **kwargs
    ) -> DataManagerLogger:
        """
        :param: spark -- Current spark session
        :param: logger_name -- Name of the logger
        :param: log_level -- Only events of this level and above will be tracked 
        :param: kwargs -- Additional keyword arguments. Possible keys are:
            - kusto_table_name: Name of the Kusto table for logging. Defaults to GC.HDS_KUSTO_TABLE_NAME.
            - scrubbers: Scrubbers to use for the logger. Defaults to None.
            - pipeline_run_id: Pipeline run id
        """
        return DataManagerLogger(
            spark,
            f"{GC.DATA_MANAGER_LOGGER}.{GC.DICOM_IMAGING}.{logger_name}",
            log_level,
            **kwargs)

    @staticmethod
    def get_silver_custom_ingestion_logger(
        spark: SparkSession,
        logger_name: str,
        log_level: int = logging.DEBUG,
        **kwargs
    ) -> DataManagerLogger:
        """
        :param: spark -- Current spark session
        :param: logger_name -- Name of the logger
        :param: log_level -- Only events of this level and above will be tracked 
        :param: kwargs -- Additional keyword arguments. Possible keys are:
            - kusto_table_name: Name of the Kusto table for logging. Defaults to GC.HDS_KUSTO_TABLE_NAME.
            - scrubbers: Scrubbers to use for the logger. Defaults to None.
            - pipeline_run_id: Fabric data pipeline run id
        """
        return DataManagerLogger(
            spark,
            f"{GC.DATA_MANAGER_LOGGER}.{GC.DATA_MANAGER_CUSTOM_SILVER_INGESTION}.{logger_name}",
            log_level,
            **kwargs)

    @staticmethod
    def get_imaging_metadata_to_fhir_logger(
        spark: SparkSession,
        logger_name: str,
        log_level: int = logging.DEBUG,
        **kwargs
    ) -> DataManagerLogger:
        """
        :param: spark -- Current spark session
        :param: logger_name -- Name of the logger
        :param: log_level -- Only events of this level and above will be tracked 
        :param: kwargs -- Additional keyword arguments. Possible keys are:
            - kusto_table_name: Name of the Kusto table for logging. Defaults to GC.HDS_KUSTO_TABLE_NAME.
            - scrubbers: Scrubbers to use for the logger. Defaults to None.
            - pipeline_run_id: Fabric data pipeline run id
        """
        return DataManagerLogger(
            spark,
            f"{GC.DATA_MANAGER_LOGGER}.{GC.DICOM_IMAGING}.{logger_name}",
            log_level,
            **kwargs)

    @staticmethod
    def get_imaging_raw_data_movement_logger(
        spark: SparkSession,
        logger_name: str,
        log_level: int = logging.DEBUG,
        **kwargs
    ) -> DataManagerLogger:
        """
        :param: spark -- Current spark session
        :param: logger_name -- Name of the logger
        :param: log_level -- Only events of this level and above will be tracked 
        :param: kwargs -- Additional keyword arguments. Possible keys are:
            - kusto_table_name: Name of the Kusto table for logging. Defaults to GC.HDS_KUSTO_TABLE_NAME.
            - scrubbers: Scrubbers to use for the logger. Defaults to None.
            - pipeline_run_id: Fabric data pipeline run id
        """
        return DataManagerLogger(
            spark,
            f"{GC.DATA_MANAGER_LOGGER}.{GC.DICOM_IMAGING}.{logger_name}",
            log_level,
            **kwargs)

    @staticmethod
    def get_sdoh_bronze_ingestion_logger(
        spark: SparkSession,
        logger_name: str,
        log_level: int = logging.DEBUG,
        **kwargs
    ) -> DataManagerLogger:
        """
        :param: spark -- Current spark session
        :param: logger_name -- Name of the logger
        :param: log_level -- Only events of this level and above will be tracked 
        :param: kwargs -- Additional keyword arguments. Possible keys are:
            - kusto_table_name: Name of the Kusto table for logging. Defaults to GC.HDS_KUSTO_TABLE_NAME.
            - scrubbers: Scrubbers to use for the logger. Defaults to None.
            - pipeline_run_id: Fabric data pipeline run id
        """
        return DataManagerLogger(
            spark,
            f"{GC.DATA_MANAGER_LOGGER}.{GC.SDOH_BRONZE_INGESTION}.{logger_name}",
            log_level,
            **kwargs)

    @staticmethod
    def get_fhirtoomop_logger(
        spark: SparkSession,
        logger_name: str,
        log_level: int = logging.DEBUG,
        **kwargs
    ) -> DataManagerLogger:
        """
        :param: spark -- Current spark session
        :param: logger_name -- Name of the logger
        :param: log_level -- Only events of this level and above will be tracked 
        :param: kwargs -- Additional keyword arguments. Possible keys are:
            - kusto_table_name: Name of the Kusto table for logging. Defaults to GC.HDS_KUSTO_TABLE_NAME.
            - scrubbers: Scrubbers to use for the logger. Defaults to None.
            - pipeline_run_id: Fabric data pipeline run id
        """
        return DataManagerLogger(
            spark,
            f"{GC.DATA_MANAGER_LOGGER}.{GC.FHIR_TO_OMOP}.{logger_name}",
            log_level,
            **kwargs)

    @staticmethod
    def get_deployment_logger(
        spark: SparkSession,
        logger_name: str,
        log_level: int = logging.DEBUG,
        **kwargs
    ) -> DataManagerLogger:
        """
        :param: spark -- Current spark session
        :param: logger_name -- Name of the logger
        :param: log_level -- Only events of this level and above will be tracked
        :param: kwargs -- Additional keyword arguments. Possible keys are:
            - kusto_table_name: Name of the Kusto table for logging. Defaults to GC.HDS_KUSTO_TABLE_NAME.
            - scrubbers: Scrubbers to use for the logger. Defaults to None.
            - pipeline_run_id: Fabric data pipeline run id
        """
        return DataManagerLogger(
            spark,
            f"{GC.DATA_MANAGER_LOGGER}.{GC.DATA_MANAGER_DEPLOYMENT}.{logger_name}",
            log_level,
            **kwargs)

    @staticmethod
    def get_fhirexport_logger(
        spark: SparkSession,
        logger_name: str,
        log_level: int = logging.DEBUG,
        **kwargs
    ) -> DataManagerLogger:
        """
        :param: spark -- Current spark session
        :param: logger_name -- Name of the logger
        :param: log_level -- Only events of this level and above will be tracked 
        :param: kwargs -- Additional keyword arguments. Possible keys are:
            - kusto_table_name: Name of the Kusto table for logging. Defaults to GC.HDS_KUSTO_TABLE_NAME.
            - scrubbers: Scrubbers to use for the logger. Defaults to None.
            - pipeline_run_id: Fabric data pipeline run id
        """
        return DataManagerLogger(
            spark,
            f"{GC.DATA_MANAGER_LOGGER}.{GC.DATA_MANAGER_FHIR_EXPORT}.{logger_name}",
            log_level,
            **kwargs)

    @staticmethod
    def get_bronzeingestion_logger(
        spark: SparkSession,
        logger_name: str,
        log_level: int = logging.DEBUG,
        **kwargs
    ) -> DataManagerLogger:
        """
        :param: spark -- Current spark session
        :param: logger_name -- Name of the logger
        :param: log_level -- Only events of this level and above will be tracked 
        :param: kwargs -- Additional keyword arguments. Possible keys are:
            - kusto_table_name: Name of the Kusto table for logging. Defaults to GC.HDS_KUSTO_TABLE_NAME.
            - scrubbers: Scrubbers to use for the logger. Defaults to None.
            - pipeline_run_id: Fabric data pipeline run id
        """
        return DataManagerLogger(
            spark,
            f"{GC.DATA_MANAGER_LOGGER}.{GC.DATA_MANAGER_BRONZE_INGESTION}.{logger_name}",
            log_level,
            **kwargs)

    @staticmethod
    def get_silveringestion_logger(
        spark: SparkSession,
        logger_name: str,
        log_level: int = logging.DEBUG,
        **kwargs
    ) -> DataManagerLogger:
        """
        :param: spark -- Current spark session
        :param: logger_name -- Name of the logger
        :param: log_level -- Only events of this level and above will be tracked
        :param: kwargs -- Additional keyword arguments. Possible keys are:
            - kusto_table_name: Name of the Kusto table for logging. Defaults to GC.HDS_KUSTO_TABLE_NAME.
            - scrubbers: Scrubbers to use for the logger. Defaults to None.
            - pipeline_run_id: Fabric data pipeline run id
        """
        return DataManagerLogger(
            spark,
            f"{GC.DATA_MANAGER_LOGGER}.{GC.DATA_MANAGER_SILVER_INGESTION}.{logger_name}",
            log_level,
            **kwargs)



    @staticmethod
    def get_omopingestion_logger(
        spark: SparkSession,
        logger_name: str,
        log_level: int = logging.DEBUG,
        **kwargs
    ) -> DataManagerLogger:
        """
        :param: spark -- Current spark session
        :param: logger_name -- Name of the logger
        :param: log_level -- Only events of this level and above will be tracked 
        :param: kwargs -- Additional keyword arguments. Possible keys are:
            - kusto_table_name: Name of the Kusto table for logging. Defaults to GC.HDS_KUSTO_TABLE_NAME.
            - scrubbers: Scrubbers to use for the logger. Defaults to None.
            - pipeline_run_id: Fabric data pipeline run id
        """
        return DataManagerLogger(
            spark,
            f"{GC.DATA_MANAGER_LOGGER}.{GC.DATA_MANAGER_OMOP_INGESTION}.{logger_name}",
            log_level,
            **kwargs)

    @staticmethod
    def get_patientoutreachgoldingestion_logger(
        spark: SparkSession,
        logger_name: str,
        log_level: int = logging.DEBUG,
        **kwargs
    ) -> DataManagerLogger:
        """
        :param: spark -- Current spark session
        :param: logger_name -- Name of the logger
        :param: log_level -- Only events of this level and above will be tracked 
        :param: kwargs -- Additional keyword arguments. Possible keys are:
            - kusto_table_name: Name of the Kusto table for logging. Defaults to GC.HDS_KUSTO_TABLE_NAME.
            - scrubbers: Scrubbers to use for the logger. Defaults to None.
            - pipeline_run_id: Fabric data pipeline run id
        """
        return DataManagerLogger(
            spark,
            f"{GC.DATA_MANAGER_LOGGER}.{GC.DATA_MANAGER_PATIENT_OUTREACH_GOLD_INGESTION}.{logger_name}",
            log_level,
            **kwargs)

    @staticmethod
    def get_cmanalyticsgoldingestion_logger(
        spark: SparkSession,
        logger_name: str,
        log_level: int = logging.DEBUG,
        **kwargs
    ) -> DataManagerLogger:
        """
        :param: spark -- Current spark session
        :param: logger_name -- Name of the logger
        :param: log_level -- Only events of this level and above will be tracked 
        :param: kwargs -- Additional keyword arguments. Possible keys are:
            - kusto_table_name: Name of the Kusto table for logging. Defaults to GC.HDS_KUSTO_TABLE_NAME.
            - scrubbers: Scrubbers to use for the logger. Defaults to None.
            - pipeline_run_id: Fabric data pipeline run id
        """
        return DataManagerLogger(
            spark,
            f"{GC.DATA_MANAGER_LOGGER}.{GC.DATA_MANAGER_CM_ANALYTICS_GOLD_INGESTION}.{logger_name}",
            log_level,
            **kwargs)

    @staticmethod
    def get_generic_logger(
        spark: SparkSession,
        logger_name: str,
        log_level: int = logging.DEBUG,
        **kwargs
    ) -> DataManagerLogger:
        """
        :param: spark -- Current spark session
        :param: logger_name -- Name of the logger
        :param: log_level -- Only events of this level and above will be tracked 
        :param: kwargs -- Additional keyword arguments. Possible keys are:
            - kusto_table_name: Name of the Kusto table for logging. Defaults to GC.HDS_KUSTO_TABLE_NAME.
            - scrubbers: Scrubbers to use for the logger. Defaults to None.
            - pipeline_run_id: Fabric data pipeline run id
        """
        return DataManagerLogger(
            spark,
            f"{GC.DATA_MANAGER_LOGGER}.{logger_name}",
            log_level,
            **kwargs)

    @staticmethod
    def get_patientoutreach_shortcuts_creation_logger(
        spark: SparkSession,
        logger_name: str,
        log_level: int = logging.DEBUG,
        **kwargs
    ) -> DataManagerLogger:
        """
        :param: spark -- Current spark session
        :param: logger_name -- Name of the logger
        :param: log_level -- Only events of this level and above will be tracked 
        :param: kwargs -- Additional keyword arguments. Possible keys are:
            - kusto_table_name: Name of the Kusto table for logging. Defaults to GC.HDS_KUSTO_TABLE_NAME.
            - scrubbers: Scrubbers to use for the logger. Defaults to None.
            - pipeline_run_id: Fabric data pipeline run id
        """
        return DataManagerLogger(
            spark,
            f"{GC.DATA_MANAGER_LOGGER}.{GC.PATIENT_OUTREACH_SHORTCUTS_CREATION_ACTIVITY_NAME}.{logger_name}",
            log_level,
            **kwargs)

    @staticmethod
    def get_patientoutreach_idm_silveringestion_logger(
        spark: SparkSession,
        logger_name: str,
        log_level: int = logging.DEBUG,
        **kwargs
    ) -> DataManagerLogger:
        """
        :param: spark -- Current spark session
        :param: logger_name -- Name of the logger
        :param: log_level -- Only events of this level and above will be tracked 
        :param: kwargs -- Additional keyword arguments. Possible keys are:
            - kusto_table_name: Name of the Kusto table for logging. Defaults to GC.HDS_KUSTO_TABLE_NAME.
            - scrubbers: Scrubbers to use for the logger. Defaults to None.
            - pipeline_run_id: Fabric data pipeline run id
        """
        return DataManagerLogger(
            spark,
            f"{GC.DATA_MANAGER_LOGGER}.{GC.DATA_MANAGER_IDM_SILVER_INGESTION}.{logger_name}",
            log_level,
            **kwargs)

    @staticmethod
    def get_sdoh_silveringestion_logger(
        spark: SparkSession,
        logger_name: str,
        log_level: int = logging.DEBUG,
        **kwargs
    ) -> DataManagerLogger:
        """
        :param: spark -- Current spark session
        :param: logger_name -- Name of the logger
        :param: log_level -- Only events of this level and above will be tracked 
        :param: kwargs -- Additional keyword arguments. Possible keys are:
            - kusto_table_name: Name of the Kusto table for logging. Defaults to GC.HDS_KUSTO_TABLE_NAME.
            - scrubbers: Scrubbers to use for the logger. Defaults to None.
            - pipeline_run_id: Fabric data pipeline run id
        """
        return DataManagerLogger(
            spark,
            f"{GC.DATA_MANAGER_LOGGER}.{GC.DATA_MANAGER_SDOH_SILVER_INGESTION}.{logger_name}",
            log_level,
            **kwargs)

    @staticmethod
    def get_ai_enrichment_metadata__logger(
        spark: SparkSession,
        logger_name: str,
        log_level: int = logging.DEBUG,
        **kwargs
    ) -> DataManagerLogger:
        """
        :param: spark -- Current spark session
        :param: logger_name -- Name of the logger
        :param: log_level -- Only events of this level and above will be tracked 
        :param: kwargs -- Additional keyword arguments. Possible keys are:
            - kusto_table_name: Name of the Kusto table for logging. Defaults to GC.HDS_KUSTO_TABLE_NAME.
            - scrubbers: Scrubbers to use for the logger. Defaults to None.
            - pipeline_run_id: Fabric data pipeline run id
        """
        return DataManagerLogger(
            spark,
            f"{GC.DATA_MANAGER_LOGGER}.{GC.DATA_MANAGER_AI_ENRICHMENT_METADATA}.{logger_name}",
            log_level,
            **kwargs)
    
    @staticmethod
    def get_ai_enrichment_ta4h_execution__logger(
        spark: SparkSession,
        logger_name: str,
        log_level: int = logging.DEBUG,
        **kwargs
    ) -> DataManagerLogger:
        """
        :param: spark -- Current spark session
        :param: logger_name -- Name of the logger
        :param: log_level -- Only events of this level and above will be tracked 
        :param: kwargs -- Additional keyword arguments. Possible keys are:
            - kusto_table_name: Name of the Kusto table for logging. Defaults to GC.HDS_KUSTO_TABLE_NAME.
            - scrubbers: Scrubbers to use for the logger. Defaults to None.
            - pipeline_run_id: Fabric data pipeline run id
        """
        return DataManagerLogger(
            spark,
            f"{GC.DATA_MANAGER_LOGGER}.{GC.DATA_MANAGER_AI_TA4H_ENRICHMENT_EXECUTION}.{logger_name}",
            log_level,
            **kwargs)
    
    @staticmethod
    def get_ai_enrichment_conversationaldata_execution__logger(
        spark: SparkSession,
        logger_name: str,
        log_level: int = logging.DEBUG,
        **kwargs
    ) -> DataManagerLogger:
        """
        :param: spark -- Current spark session
        :param: logger_name -- Name of the logger
        :param: log_level -- Only events of this level and above will be tracked 
        :param: kwargs -- Additional keyword arguments. Possible keys are:
            - kusto_table_name: Name of the Kusto table for logging. Defaults to GC.HDS_KUSTO_TABLE_NAME.
            - scrubbers: Scrubbers to use for the logger. Defaults to None.
            - pipeline_run_id: Fabric data pipeline run id
        """
        return DataManagerLogger(
            spark,
            f"{GC.DATA_MANAGER_LOGGER}.{GC.DATA_MANAGER_AI_CONVERSATIONALDATA_ENRICHMENT_EXECUTION}.{logger_name}",
            log_level,
            **kwargs)
        
    @staticmethod
    def get_ai_enrichment_mii_execution__logger(
        spark: SparkSession,
        logger_name: str,
        log_level: int = logging.DEBUG,
        **kwargs
    ) -> DataManagerLogger:
        """
        :param: spark -- Current spark session
        :param: logger_name -- Name of the logger
        :param: log_level -- Only events of this level and above will be tracked 
        :param: kwargs -- Additional keyword arguments. Possible keys are:
            - kusto_table_name: Name of the Kusto table for logging. Defaults to GC.HDS_KUSTO_TABLE_NAME.
            - scrubbers: Scrubbers to use for the logger. Defaults to None.
            - pipeline_run_id: Fabric data pipeline run id
        """
        return DataManagerLogger(
            spark,
            f"{GC.DATA_MANAGER_LOGGER}.{GC.DATA_MANAGER_AI_MII_ENRICHMENT_EXECUTION}.{logger_name}",
            log_level,
            **kwargs)

        
    @staticmethod
    def get_ai_enrichment_execution__logger(
        spark: SparkSession,
        logger_name: str,
        log_level: int = logging.DEBUG,
        **kwargs
    ) -> DataManagerLogger:
        """
        :param: spark -- Current spark session
        :param: logger_name -- Name of the logger
        :param: log_level -- Only events of this level and above will be tracked 
        :param: kwargs -- Additional keyword arguments. Possible keys are:
            - kusto_table_name: Name of the Kusto table for logging. Defaults to GC.HDS_KUSTO_TABLE_NAME.
            - scrubbers: Scrubbers to use for the logger. Defaults to None.
            - pipeline_run_id: Fabric data pipeline run id
        """
        return DataManagerLogger(
            spark,
            f"{GC.DATA_MANAGER_LOGGER}.{GC.DATA_MANAGER_AI_ENRICHMENT_EXECUTION}.{logger_name}",
            log_level,
            **kwargs)
        
    @staticmethod
    def get_ai_enrichment_mip_execution__logger(
        spark: SparkSession,
        logger_name: str,
        log_level: int = logging.DEBUG,
        **kwargs
    ) -> DataManagerLogger:
        """
        :param: spark -- Current spark session
        :param: logger_name -- Name of the logger
        :param: log_level -- Only events of this level and above will be tracked 
        :param: kwargs -- Additional keyword arguments. Possible keys are:
            - kusto_table_name: Name of the Kusto table for logging. Defaults to GC.HDS_KUSTO_TABLE_NAME.
            - scrubbers: Scrubbers to use for the logger. Defaults to None.
        """
        return DataManagerLogger(
            spark,
            f"{GC.DATA_MANAGER_LOGGER}.{GC.DATA_MANAGER_AI_MIP_ENRICHMENT_EXECUTION}.{logger_name}",
            log_level,
            **kwargs)

    @staticmethod
    def get_business_events_ingestion_logger(
        spark: SparkSession,
        logger_name: str,
        log_level: int = logging.DEBUG,
        **kwargs
    ) -> DataManagerLogger:
        """
        :param: spark -- Current spark session
        :param: logger_name -- Name of the logger
        :param: log_level -- Only events of this level and above will be tracked 
        :param: kwargs -- Additional keyword arguments. Possible keys are:
            - kusto_table_name: Name of the Kusto table for logging. Defaults to GC.HDS_KUSTO_TABLE_NAME.
            - scrubbers: Scrubbers to use for the logger. Defaults to None.
        """
        return DataManagerLogger(
            spark,
            f"{GC.DATA_MANAGER_LOGGER}.{GC.DATA_MANAGER_BUSINESS_EVENTS_INGESTION}.{logger_name}",
            log_level,
            **kwargs)
        
        
    @staticmethod
    def get_run_id():
        """
        Set the run id
        """
        if LoggingHelper.run_id is None:
            LoggingHelper.run_id = str(uuid.uuid4())

        return LoggingHelper.run_id
