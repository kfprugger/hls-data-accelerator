from pyspark.sql import SparkSession
from microsoft.fabric.hls.hds.errors.thread_pool_manager_failed_error import ThreadPoolManagerFailedError
from microsoft.fabric.hls.hds.utils.logging_helper import LoggingHelper
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.errors.streaming_queries_failed_error import StreamingQueriesFailedError

import concurrent.futures

class ThreadPoolManager:

    def __init__(self, spark: SparkSession):
        """
            Initialize thread pool manager
            Args:
            spark: spark session
        """
        self.spark: SparkSession = spark
        self._logger = LoggingHelper.get_generic_logger(
            self.spark, self.__class__.__name__, GlobalConstants.LOGGING_LEVEL)
        
    def await_all_termination(self, futures):
        """Block until all tasks have completed on the executor

        Args:
            futures (_type_): List of threadpool tasks to monitor

        Raises:
            ThreadPoolManagerFailedError: Raise an exception if any of the threads terminate in error
        """
        self._logger.info(f"{LC.BEGAN_EXECUTION_INFO_MSG}")
        exceptions = []
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as ex:
                exceptions.append(ex)
        
        if exceptions:
            raise ThreadPoolManagerFailedError(exceptions)

        self._logger.info(f"{LC.COMPLETED_EXECUTION_INFO_MSG}")