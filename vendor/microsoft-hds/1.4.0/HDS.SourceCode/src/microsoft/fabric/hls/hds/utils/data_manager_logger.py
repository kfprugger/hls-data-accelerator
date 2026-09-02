# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
import sys
import logging
import os
import uuid
import inspect
from pyspark.sql import SparkSession
from microsoft.fabric.hls.hds.utils.spark_logger import SparkLogger
from microsoft.fabric.hls.hds.utils.SparkLoggerAppInsights import SparkLoggerAppInsights
from microsoft.fabric.hls.hds.utils.kusto_spark_logger import KustoSparkLogger
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.utils.utils import Utils

class DataManagerLogger():
    '''
    Class for logging operations

    The log will include the severity level, timestamp, logger name, and message
    
    :param: spark -- Current spark session
    :param: logger_name -- the name of the logger
    :param: log_level -- only events of this level and above will be tracked 
    :param: kwargs -- Additional keyword arguments. Possible keys are:
            - kusto_table_name: Name of the Kusto table for logging. Defaults to GC.HDS_KUSTO_TABLE_NAME.
            - scrubbers: Scrubbers to use for the logger. Defaults to None.
            - pipeline_run_id: Pipeline run id. Defaults to None.
            - run_id: Run id. Defaults to None.
    '''
    
    def __init__(self, spark: SparkSession, 
                 logger_name: str,
                 log_level: int = logging.DEBUG, 
                 **kwargs):
        
        log_format = logging.Formatter("%(asctime)s::%(name)s::%(levelname)s::%(message)s")
        
        # Initialize init arguments
        self._spark = spark
        self._logger_name = logger_name
        self._log_level = log_level
        self._pipeline_run_id = kwargs.get('pipeline_run_id', None)
        self._run_id = kwargs.get('run_id', str(uuid.uuid4()))
        
        # Get kusto_table_name and scrubbers from kwargs
        self._kusto_table_name = kwargs.get('kusto_table_name', GC.HDS_KUSTO_TABLE_NAME)
        self._scrubbers = kwargs.get('scrubbers', None)
        self._log_kusto = Utils.get_enable_hds_logs_config(spark=self._spark)
        
        # Set up stdout_logger
        console_handler = logging.StreamHandler(sys.stdout) 
        console_handler.setFormatter(log_format)
        stdoutLoggerName = f"{LC.ConsoleLoggerName.format(logger_name=logger_name)}"
        self._stdout_logger = logging.getLogger(stdoutLoggerName)
        if (self._stdout_logger.hasHandlers()):
            self._stdout_logger.handlers.clear()
        self._stdout_logger.addHandler(console_handler) 
        # Set console logger log level based on environment variable
        self._stdout_logger.setLevel(GC.DEBUG_LOGGING_LEVEL if os.getenv('ENABLE_CONSOLE_DEBUG_LOGGING', 'false').lower() == 'true' else GC.LOGGING_LEVEL)
        
        self._stdout_logger.propagate = False
        
        # Set up spark loggers
        self._spark_logger = SparkLogger.get_logger(self._spark, self._logger_name, self._log_level)
        self._spark_logger_app_insights = SparkLoggerAppInsights.get_logger(spark=self._spark, 
                                                                            run_id=self._run_id, 
                                                                            logger_name=self._logger_name, 
                                                                            pipeline_run_id=self._pipeline_run_id,
                                                                            log_level=self._log_level) 
        self._kusto_spark_logger = None
        
        # Only initialize Kusto logger if log_kusto is True. This is set to True by default
        if self._log_kusto:
            self._kusto_spark_logger = KustoSparkLogger.get_logger(
                kusto_table_name = self._kusto_table_name,
                run_id = self._run_id,
                logger_name = self._logger_name, 
                pipeline_run_id = self._pipeline_run_id,
                log_level = self._log_level,
                scrubbers=self._scrubbers
            )

    def debug(self, message: str, *args, **kwargs):
        '''
        A utility method to log at the DEBUG level
        
        :param: message -- the message to be logged
        :param: args/kargs -- (optional) a list of additional arguments 
        '''
        func = inspect.currentframe().f_back.f_code
        self._post_data(logging.DEBUG, message, func, *args, **kwargs)
    
    def info(self, message: str, *args, **kwargs):
        '''
        A utility method to log at the INFO level
        
        :param: message -- the message to be logged
        :param: args/kargs -- (optional) a list of additional arguments 
        '''
        func = inspect.currentframe().f_back.f_code
        self._post_data(logging.INFO, message, func, *args, **kwargs)
    
    def warning(self, message: str, *args, **kwargs):
        '''
        A utility method to log at the WARNING level
        
        :param: message -- the message to be logged
        :param: args/kargs -- (optional) a list of additional arguments 
        '''
        func = inspect.currentframe().f_back.f_code
        self._post_data(logging.WARNING, message, func, *args, **kwargs)
    
    def error(self, message: str, *args, **kwargs):
        '''
        A utility method to log at the ERROR level
        
        :param: message -- the message to be logged
        :param: args/kargs -- (optional) a list of additional arguments 
        '''
        func = inspect.currentframe().f_back.f_code
        self._post_data(logging.ERROR, message, func, *args, **kwargs)
    
    def critical(self, message: str, *args, **kwargs):
        '''
        A utility method to log at the CRITICAL level
        
        :param: message -- the message to be logged
        :param: args/kargs -- (optional) a list of additional arguments 
        '''
        func = inspect.currentframe().f_back.f_code
        self._post_data(logging.CRITICAL, message, func, *args, **kwargs)
        
    def _post_data(self, level: int, message: str, func, *args, **kwargs):
        '''
        A utility method to encapsulate sending messages at the specified level
        
        :params: level -- the severity level of the statement
        :params: message -- the message to be logged
        '''
        
        logging_message = f"{func.co_name}::{LC.RunId}::{self._run_id}::{message}"
        self._stdout_logger.log(level, logging_message, *args, **kwargs)
        self._spark_logger.log(level, logging_message)
        self._spark_logger_app_insights.log(level, logging_message, *args, **kwargs)
        
        # Only log to Kusto if the Kusto Spark Logger is instantiated
        if self._kusto_spark_logger:
            self._kusto_spark_logger.log(level, logging_message, *args, **kwargs)
    
    def set_run_id(self, run_id: str) -> None:
        """
        Sets the run ID for the logger.

        Args:
            run_id (str): The run ID to set.
        """
        self._run_id = run_id
        self._spark_logger_app_insights.set_run_id(run_id)
        if self._kusto_spark_logger:
            self._kusto_spark_logger.set_run_id(run_id)
    
    
