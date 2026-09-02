"""
This package creates global Logger
"""
import abc
import logging
import os
import uuid
from typing import Mapping

from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry.environment_variables import OTEL_METRICS_EXPORTER, OTEL_TRACES_EXPORTER
from pyspark.sql import SparkSession


class CustomDimensionsFilter(logging.Filter):
    """Add application-wide properties to LogHandler records"""
    def __init__(self, custom_dimensions=None):
        super().__init__()
        self.custom_dimensions = custom_dimensions or {}

    def filter(self, record):
        """Adds the default custom_dimensions into the current log record"""
        cdim = self.custom_dimensions.copy()
        cdim.update({
            "LogLevel": record.levelname,
            "LoggerName": record.name,
            "FunctionName": record.funcName,
            "LineNumber": record.lineno,
        })
        cdim.update(getattr(record, 'custom_dimensions', {}))
        for key, value in cdim.items():
            setattr(record, key, value)
        return True


class IDTTLogger(abc.ABC):
    @abc.abstractmethod
    def info(self, message: str):
        pass

    @abc.abstractmethod
    def error(self, message: str, extra: Mapping[str, object] | None = None):
        pass

    @abc.abstractmethod
    def debug(self, message: str):
        pass

    @abc.abstractmethod
    def warn(self, message: str):
        pass


class Logger(IDTTLogger):
    _LOGGER_NAME = "DTT"
    _app_insight_logger = None
    _spark_logger = None

    @classmethod
    def init_logger(cls):
        spark = SparkSession.builder.getOrCreate()
        if cls._spark_logger is None:
            cls._spark_logger = spark._jvm.org.apache.log4j.LogManager.getLogger(cls._LOGGER_NAME)

        instrumentation_key = spark.conf.get("spark.dtt.application_insights.instrumentation_key", None)
        if instrumentation_key and cls._app_insight_logger is None:
            configured_run_id = spark.conf.get("spark.dtt.logger.run_id", None)
            # Set the run id which identifies the current run
            if configured_run_id:
                run_id = configured_run_id
            else:
                run_id = uuid.uuid4().__str__()
                spark.conf.set("spark.dtt.logger.run_id", run_id)
            print(f"Initializing logger, Run ID: {run_id}")

            configure_azure_monitor(connection_string=instrumentation_key, logger_name=cls._LOGGER_NAME)
            cls._app_insight_logger = logging.getLogger(cls._LOGGER_NAME)
            cls._app_insight_logger.setLevel(logging.DEBUG)
            cls._app_insight_logger.addFilter(CustomDimensionsFilter({"RunId": str(run_id)}))

    @staticmethod
    def info(message: str):
        Logger._spark_logger.info(message)
        if Logger._app_insight_logger:
            Logger._app_insight_logger.info(message)

    @staticmethod
    def error(message: str, extra: Mapping[str, object] | None = None):
        Logger._spark_logger.error(message)
        if Logger._app_insight_logger:
            if extra:
                custom_filter = CustomDimensionsFilter(extra)
                Logger._app_insight_logger.addFilter(custom_filter)
                Logger._app_insight_logger.error(message)
                Logger._app_insight_logger.removeFilter(custom_filter)
            else:
                Logger._app_insight_logger.error(message)

    @staticmethod
    def debug(message: str):
        Logger._spark_logger.debug(message)
        if Logger._app_insight_logger:
            Logger._app_insight_logger.debug(message)

    @staticmethod
    def warn(message: str):
        Logger._spark_logger.warn(message)
        if Logger._app_insight_logger:
            Logger._app_insight_logger.warning(message)

    @staticmethod
    def _disable_unused_opentelemetry_exporters():
        '''
        This function disables the default OpenTelemetry metrics and traces exporters by setting the
        corresponding environment variables to "None". It is used to suppress warnings when calling
        `configure_azure_monitor` function.
        '''
        os.environ[OTEL_METRICS_EXPORTER] = "None"
        os.environ[OTEL_TRACES_EXPORTER] = "None"

    @classmethod
    def _cleanup_old_handlers(cls):
        for index, _ in enumerate(logging.getLogger(cls._LOGGER_NAME).handlers):
            logging.getLogger(cls._LOGGER_NAME).handlers.pop(index)
