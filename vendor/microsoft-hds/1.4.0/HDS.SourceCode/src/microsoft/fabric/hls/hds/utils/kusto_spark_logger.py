# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
import logging
import importlib.util
from typing import Mapping, Optional
import uuid
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.utils.SparkLoggerAbstractBaseClass import ABCSparkLogger
from microsoft.fabric.hls.hds.utils.kusto_scrubbers import IScrub

class KustoSparkLogger(ABCSparkLogger):
    """
    Class for wrapping setup for the Spark Kusto logger
    """
    def __init__(self, 
                 kusto_table_name: str, 
                 logger_name: str, 
                 **kwargs
                 ) -> None:
        """
        Initialize the KustoSparkLogger.

        Args:
            kusto_table_name (str): The name of the Kusto table.
            run_id (str): The unique identifier for the run.
            logger_name (str): The name of the logger.
            pipeline_run_id (str): The Fabric data pipeline run ID.
            log_level (int): The level of the logger.
            scrubbers (Optional[list[IScrub]]): The list of scrubbers.
        """
        if not kusto_table_name:
            raise ValueError("The kusto_table_name cannot be empty")
        
        self.kusto_spark_logger = None
        self.kusto_table_name = kusto_table_name
        self._log_level = kwargs.get('log_level', logging.INFO)
        self._run_id = kwargs.get('run_id', None)
        self._pipeline_run_id = kwargs.get('pipeline_run_id', None)
        self._logger_name = logger_name
        self._scrubbers = kwargs.get('scrubbers', None)
        
        self._setup_logger()
        
    def _setup_logger(self):
        """
        Set up the logger.
        """
        if self._check_module_availability("synapse.ml"):
            from synapse.ml.pymds.handler import default_scrubbers
            from microsoft.fabric.hls.hds.utils.fabric_mds_handler import FabricMDSHandler
            from microsoft.fabric.hls.hds.utils.kusto_scrubbers import GuidScrubber
            
            self.kusto_spark_logger = logging.getLogger(f"{LC.KustoSparkLoggerName.format(logger_name=self._logger_name)}")
            
            hds_default_scrubbers = [*default_scrubbers, GuidScrubber()]
        
            # If scrubbers are passed, extend hds_default_scrubbers with them
            if self._scrubbers is not None:
                hds_default_scrubbers.extend(self._scrubbers)
            
            if (self.kusto_spark_logger.hasHandlers()):
                self.kusto_spark_logger.handlers.clear()

            handler = FabricMDSHandler(tableName=self.kusto_table_name, scrubbers=hds_default_scrubbers)
            handler.setLevel(self._log_level)
            
            self.kusto_spark_logger.addHandler(handler)            
            self.kusto_spark_logger.setLevel(self._log_level)
            self.kusto_spark_logger.propagate = False
        else:
            print(f"SynapseML module not available. Logging to Kusto table {self.kusto_table_name} will not be enabled.")
            
    def info(self, message: str, extra: Mapping[str, object]=None):
        """
        Log an info level message.

        Args:
            message (str): The message to log.
            extra (Mapping[str, object]): Extra information to log.
        """
        if self.kusto_spark_logger:
            self.kusto_spark_logger.info(message, extra=extra)
        else:
            super().info(message, extra=extra)

    def error(self, message: str, extra: Mapping[str, object]=None):
        """
        Log an error level message.

        Args:
            message (str): The message to log.
            extra (Mapping[str, object]): Extra information to log.
        """
        if self.kusto_spark_logger:
            self.kusto_spark_logger.error(message, extra=extra)
        else:
            super().error(message, extra=extra)

    def debug(self, message: str, extra: Mapping[str, object]=None):
        """
        Log a debug level message.

        Args:
            message (str): The message to log.
            extra (Mapping[str, object]): Extra information to log.
        """
        if self.kusto_spark_logger:
            self.kusto_spark_logger.debug(message, extra=extra)
        else:
            super().debug(message, extra=extra)

    def warning(self, message: str, extra: Mapping[str, object]=None):
        """
        Log a warning level message.

        Args:
            message (str): The message to log.
            extra (Mapping[str, object]): Extra information to log.
        """
        if self.kusto_spark_logger:
            self.kusto_spark_logger.warning(message, extra=extra)
        else:
            super().warning(message, extra=extra)

    def critical(self, message: str, extra: Mapping[str, object]=None):
        """
        Log a critical level message.

        Args:
            message (str): The message to log.
            extra (Mapping[str, object]): Extra information to log.
        """
        if self.kusto_spark_logger:
            self.kusto_spark_logger.critical(message, extra=extra)
        else:
            super().critical(message, extra=extra)

    def log(self, level: int, msg: str, **kwargs):
        """
        Log a message with the specified level.

        Args:
            level (int): The level of the log.
            msg (str): The message to log.
            **kwargs: Extra keyword arguments.
        """
        extra = kwargs.get('extra', None)
        # Add defualt custom dimensions
        extra = self._extra_add_default_custom_dimensions(extra)
        # Passes the given severity level and calls the python logger
        if level == logging.DEBUG:
            self.debug(msg, extra=extra)
        elif level == logging.INFO:
            self.info(msg, extra=extra)
        elif level == logging.WARNING:
            self.warning(msg, extra=extra)
        elif level == logging.ERROR:
            self.error(msg, extra=extra)
        elif level == logging.CRITICAL:
            self.critical(msg, extra=extra)
    
    @staticmethod
    def get_logger(kusto_table_name: str, 
                   run_id: str, 
                   logger_name: str, 
                   log_level: int, 
                   pipeline_run_id: str = None,
                   scrubbers: Optional[list[IScrub]] = None):
        """
        Get a logger.

        Args:
            kusto_table_name (str): The name of the Kusto table.
            run_id (str): The unique identifier for the run.
            logger_name (str): The name of the logger.
            log_level (int): The level of the logger.
            pipeline_run_id (str): The Fabric data pipeline run ID.
            scrubbers (Optional[list[IScrub]]): The list of scrubbers.

        Returns:
            KustoSparkLogger: The logger.
        """
        logger = KustoSparkLogger(kusto_table_name=kusto_table_name, 
                                  run_id=run_id, 
                                  logger_name=logger_name, 
                                  log_level=log_level, 
                                  pipeline_run_id=pipeline_run_id,
                                  scrubbers=scrubbers)
        return logger
        
    def _check_module_availability(self, module_name):
        """
        Check the availability of a module.

        Args:
            module_name (str): The name of the module.

        Returns:
            bool: True if the module is available, False otherwise.
        """
        # Attempt to find the module
        try: 
            return importlib.util.find_spec(module_name) is not None
        except (ModuleNotFoundError, ValueError):
            return False
    
    def _extra_add_default_custom_dimensions(self, extra: Mapping[str, object] | None = None) -> Mapping[str, object]:
        """
        Add default custom dimensions to extra.

        Args:
            extra (Mapping[str, object] | None): The extra information.

        Returns:
            Mapping[str, object]: The extra information with default custom dimensions.
        """
        if extra is None:
            extra = {}

        # Add the run ID and the pipeline run id to the extra dictionary
        extra["RunId"] = str(self._run_id)
        extra["PipelineRunId"] = str(self._pipeline_run_id) if self._pipeline_run_id else ""
        return extra
    
    def set_run_id(self, run_id: str) -> None:
        self._run_id = run_id