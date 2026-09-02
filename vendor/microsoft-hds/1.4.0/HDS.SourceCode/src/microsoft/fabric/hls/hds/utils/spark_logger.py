import logging
from pyspark.sql import SparkSession
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC

class SparkLogger:
    """
    Class for wrapping setup for the Spark logger
    """
    def __init__(self, spark: SparkSession, logger_name: str, log_level: int) -> None:
        self._spark = spark
        self._logger_name = f"{LC.LogAnalyticsSparkLoggerName.format(logger_name=logger_name)}"
        self._log_level = log_level
        self._sc = self._spark._jvm.org.apache.log4j # type: ignore
        
        # Creates the actual spark logger
        self.spark_logger = self._sc.LogManager.getLogger(self._logger_name) 
        # Set lowest severity level threshold
        self.spark_logger.setLevel(self._level_selector(log_level))

    def log(self, level: int, msg: str):
        # Passes the given severity level and calls the native py4j logging methods
        if level == logging.DEBUG:
            self.spark_logger.debug(msg)
        elif level == logging.INFO:
            self.spark_logger.info(msg)
        elif level == logging.WARNING:
            self.spark_logger.warn(msg)
        elif level == logging.ERROR:
            self.spark_logger.error(msg)
        elif level == logging.CRITICAL:
            self.spark_logger.fatal(msg)

    @staticmethod
    def get_logger(spark: SparkSession, logger_name: str, log_level: int = logging.DEBUG):
        """
        Passes the message from the Logger wrapper to the spark logger object

        :param: logger_name -- name of the logger
        :param: log_level -- logging level
        """
        logger = SparkLogger(spark, logger_name, log_level)
        return logger

    def _level_selector(self, log_level: int):
        if log_level == logging.DEBUG:
            return self._sc.Level.DEBUG
        elif log_level == logging.INFO:
            return self._sc.Level.INFO
        elif log_level == logging.WARNING:
            return self._sc.Level.WARNING
        elif log_level == logging.ERROR:
            return self._sc.Level.ERROR
        elif log_level == logging.CRITICAL:
            return self._sc.Level.CRITICAL
