import logging
from pyspark.sql import SparkSession
from opencensus.ext.azure.log_exporter import AzureLogHandler
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.utils.SparkLoggerAbstractBaseClass import ABCSparkLogger
from microsoft.fabric.hls.hds.utils.SparkLoggerCustomDimensions import CustomDimensionsFilter
from microsoft.fabric.hls.hds.utils.utils import Utils
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase


class SparkLoggerAppInsights(ABCSparkLogger):
    """
    Class for wrapping setup for the Spark logger
    """
    
    def __init__(
        self,
        spark: SparkSession,
        logger_name: str,
        log_level: int, 
        **kwargs
        ) -> None:
        """
        Initializes the SparkLoggerAppInsights.

        Args:
            spark (SparkSession): The current Spark session.
            logger_name (str): The name of the logger.
            log_level (int): The log level for the logger.
            **kwargs: Additional keyword arguments. Possible keys are:
                - run_id (str): The run ID for the logger. Defaults to None.
                - pipeline_run_id (str): The pipeline run ID for the logger. Defaults to None.
                - mssparkutils_client (MSSparkUtilsClientBase): The mssparkutils client. Defaults to None.
        """
        self._spark = spark
        self.spark_logger = None
        self.mssparkutils_client = Utils.get_mssparkutils_client(kwargs.get('mssparkutils_client', None))

        instrumentation_key = Utils.get_app_insights_instrumentation_key(spark, self.mssparkutils_client)
        if instrumentation_key:
            try:
                handler = AzureLogHandler(connection_string = instrumentation_key)
            except Exception as e:
                raise ValueError("Invalid connection string for AzureLogHandler") from e
            
            formatter = logging.Formatter('%(message)s')
            handler.setFormatter(formatter)
            handler.setLevel(log_level)

            handler.addFilter(CustomDimensionsFilter({"RunId": kwargs.get('run_id', None)}))
            handler.addFilter(CustomDimensionsFilter({"PipelineRunId": kwargs.get('pipeline_run_id', None)}))
            self.spark_logger = logging.getLogger(f"{LC.AppInsightsSparkLoggerName.format(logger_name=logger_name)}")
            # Clean up handlers
            if (self.spark_logger.hasHandlers()):
                self.spark_logger.handlers.clear()
            self.spark_logger.addHandler(handler) 
            self.spark_logger.setLevel(log_level)
            self.spark_logger.propagate = False

    def info(self, message: str, **kwargs):
        if self.spark_logger:
            self.spark_logger.info(message, **kwargs)
        else:
            super().info(message)

    def error(self, message: str, **kwargs):
        if self.spark_logger:
            self.spark_logger.error(message, **kwargs)
        else:
            super().error(message)

    def debug(self, message: str, **kwargs):
        if self.spark_logger:
            self.spark_logger.debug(message)
        else:
            super().debug(message, **kwargs)

    def warning(self, message: str, **kwargs):
        if self.spark_logger:
            self.spark_logger.warning(message, **kwargs)
        else:
            super().warning(message, **kwargs)

    def critical(self, message: str, **kwargs):
        if self.spark_logger:
            self.spark_logger.critical(message, **kwargs)
        else:
            super().critical(message, **kwargs)

    def log(self, level: int, msg: str, **kwargs):
        # Passes the given severity level and calls the native py4j logging methods
        if level == logging.DEBUG:
            self.debug(msg, **kwargs)
        elif level == logging.INFO:
            self.info(msg, **kwargs)
        elif level == logging.WARNING:
            self.warning(msg, **kwargs)
        elif level == logging.ERROR:
            self.error(msg)
        elif level == logging.CRITICAL:
            self.critical(msg, **kwargs)

    def set_run_id(self, run_id: str) -> None:
        """
        Sets the run ID for the logger.

        Args:
            run_id (str): The run ID to set.
        """
        if self.spark_logger:
            for handler in self.spark_logger.handlers:
                for filter in handler.filters:
                    if isinstance(filter, CustomDimensionsFilter):
                        filter.custom_dimensions["RunId"] = run_id
    @staticmethod
    def get_logger(spark: SparkSession, 
                   run_id: str, 
                   logger_name: str, 
                   pipeline_run_id: str = None,
                   log_level: int = logging.DEBUG):
        """
        Passes the message from the Logger wrapper to the spark logger object

        :param: logger_name -- name of the logger
        :param: log_level -- logging level
        """
        logger = SparkLoggerAppInsights(spark=spark, 
                                        run_id=run_id, 
                                        logger_name=logger_name, 
                                        pipeline_run_id=pipeline_run_id,
                                        log_level=log_level)
        return logger