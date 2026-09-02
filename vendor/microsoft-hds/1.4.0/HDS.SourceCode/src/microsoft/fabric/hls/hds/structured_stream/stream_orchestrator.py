import json
import re
from threading import Thread
import time
from typing import Any, Callable, List, Optional
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.streaming import StreamingQuery
from microsoft.fabric.hls.hds.structured_stream.streaming_query_accumulator import StreamingQueryAccumulator
from microsoft.fabric.hls.hds.utils.logging_helper import LoggingHelper
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.errors.streaming_queries_failed_error import StreamingQueriesFailedError
from microsoft.fabric.hls.hds.utils.utils import Utils

class StreamingQueryInfo:

    def __init__(
        self,
        query_name: str,
        checkpoint_path: str,
        streaming_dataframe: DataFrame,
        batch_fn: Callable[[DataFrame, Any], Any],
        data_format: Optional[str] = None):

        self.query_name = query_name
        self.checkpoint_path = checkpoint_path
        self.streaming_dataframe = streaming_dataframe
        self.batch_fn = batch_fn
        self.data_format = data_format

class StreamOrchestrator():

    def __init__(
        self,
        spark: SparkSession,
        max_structured_streaming_queries: Optional[int],
        **kwargs):
        """
            Args:
            spark: spark session
            max_structured_streaming_queries [Optional]: The max number of running structured streaming queries
        """
        self.spark: SparkSession = spark
        self.max_structured_streaming_queries = max_structured_streaming_queries
        self.sleep_in_seconds = GlobalConstants.STREAM_ORCHESTRATOR_SLEEP_IN_SECONDS
        self.terminated = False
        
        if "logger" in kwargs:
            self._logger = kwargs.get("logger")
        else:
            self._logger = LoggingHelper.get_generic_logger(
                self.spark, self.__class__.__name__, GlobalConstants.LOGGING_LEVEL)
        
        self.streaming_query_accumulator = StreamingQueryAccumulator(self._logger)
        spark.streams.addListener(self.streaming_query_accumulator)

        self._active_streaming_queries: List[StreamingQuery] = []
        self._streaming_request_queue: List[StreamingQueryInfo] = []
        self._terminated_queries: List[StreamingQuery] = []
        self.streaming_query_processor = None
        self.failed_queries = []
    
    def __start_query_processor(self):
        # Start background processing thread
        self.streaming_query_processor = Thread(target=self._process_streaming_queries)
        self.streaming_query_processor.start()
    
    def await_all(self) -> None:
        """
            Description: 
                Await until all queries have been terminated, this includes exhausting the set of queued queries
        """
        self.terminated = True
        if self.streaming_query_processor:
            self.streaming_query_processor.join()
        
        self.spark.streams.removeListener(self.streaming_query_accumulator)

        if len(self.failed_queries) > 0:
            raise StreamingQueriesFailedError(f"The following queries failed: {self.failed_queries}")
    
    def get_streaming_metrics(self) -> dict:
        if self.streaming_query_accumulator:
            return self.streaming_query_accumulator.get_streaming_data()
        else:
            return {}

    def check_stream_success(self, streaming_query) -> bool:
        """
            Description:
                Check the success status of a streaming query
        Args:
            streaming_query: The streaming query to be checked for the success status
        """
        for query in self._terminated_queries:
            if query.name == streaming_query:  
                return (query.exception() is None)
        return False        

    def enqueue_streaming_query(self, streaming_query_info: StreamingQueryInfo) -> None:
        """
            Description:
                Enqueue a streaming query to be processed

        Args:
            streaming_query_info (StreamingQueryInfo): The info needed to create the streaming query
        """
        if self.streaming_query_processor is None:
            self.__start_query_processor()
        
        self._logger.info(f"Enqueuing streaming query: {streaming_query_info.query_name}")
        self._streaming_request_queue.append(streaming_query_info)

    def _process_streaming_queries(self) -> None:
        """
        Description:
            Processes streaming queries until both queues are exhausted and termination is requested

        Raises:
            StreamingQueriesFailedError: Raise an exception if any of the queries terminate in error
        """
        
        print("Stream processor started")
        
        # We need to block until all queries are terminated
        while not self.terminated or (self._active_streaming_queries or self._streaming_request_queue):
            try:
                self._update_streams()
                self._logger.info(f"Active: {len(self.spark.streams.active)}, Queued: {len(self._streaming_request_queue)}, Terminated: {len(self._terminated_queries)}")                
                time.sleep(self.sleep_in_seconds)
                    
            except Exception as e:
                self._logger.error(f"Update streaming error: {e}")

        self.failed_queries = [
            f"{streaming_query.id}:{streaming_query.name}: Exception details: {streaming_query.exception()}"
            for streaming_query in self._terminated_queries
            if streaming_query.exception() is not None
        ]

        self._logger.info(f"{LC.STREAM_ORCHESTRATOR_END_QUERIES_INFO_MSG}")
    
    def _update_streams(self) -> None:
        """
            Description:
                Updates the current state of queued, active and terminated queries
        """

        # Get active and terminated queries
        active_queries: List[StreamingQuery] = []
        terminated_queries: List[StreamingQuery] = []
        active_queries, terminated_queries = Utils.split(self._active_streaming_queries, lambda s: s.isActive)

        self._terminated_queries.extend(terminated_queries)
        
        self._active_streaming_queries = active_queries

        # Start any new queries
        count_of_streams_to_start = self._get_count_of_streams_to_start()
        self._start_queued_streaming_queries(count_of_streams_to_start)

    def _await_stream_termination(self) -> None:
        if self.spark.streams.active:

            # Block until any of the queries on the associated SQLContext has terminated
            self.spark.streams.awaitAnyTermination()
            self.spark.streams.resetTerminated()
    
    def _get_count_of_streams_to_start(self) -> int:
        """
        Description: Determine the amount of streaming queries to start given the current number of active streams
                     and whether or not the number of streams is limited

        Returns:
            int: The number of streams to enqueue
        """
        if self.spark.streams.active:
            if self.max_structured_streaming_queries is not None:
                count_of_streams_to_start = max(self.max_structured_streaming_queries - len(self.spark.streams.active), 0)
            else:
                count_of_streams_to_start = len(self._streaming_request_queue)
        else:
            # No active streams, but there are streams ready to start in the queue
            if self.max_structured_streaming_queries is not None:
                count_of_streams_to_start = min(self.max_structured_streaming_queries, len(self._streaming_request_queue))
            else:
                count_of_streams_to_start = len(self._streaming_request_queue)
            
        return count_of_streams_to_start
            
    def _start_queued_streaming_queries(self, count_of_streaming_queries_to_start: int) -> None:
        """
        Description:
            start queued streaming queries - pop the first n streaming queries from the queue and start them

        Args:
            count_of_streaming_queries_to_start: int - The number of queries to start

        Returns:
            None
        """
        for _ in range(count_of_streaming_queries_to_start):
            if len(self._streaming_request_queue) > 0:
                streaming_query_info = self._streaming_request_queue.pop(0)
                self._logger.info(f"Starting streaming query: {streaming_query_info.query_name}")
                streaming_query = self._start_streaming_query(streaming_query_info)
                self._logger.info(f"Started streaming query: {streaming_query_info.query_name}")
                self._active_streaming_queries.append(streaming_query)
            else:
                return
    
    def _start_streaming_query(
        self,
        streaming_query_info: StreamingQueryInfo
    ) -> StreamingQuery:
        """
        Description:
            start streaming query - Use foreachbatch to call a custom transformation function for each batch

        Args:
            streaming_query_info: StreamingQueryInfo - The info needed to create the streaming query

        Returns:
            A new `StreamingQuery`
        """
        df: DataFrame = streaming_query_info.streaming_dataframe
        if streaming_query_info.data_format:
            write_stream = df.writeStream.format(streaming_query_info.data_format)
        else:
            write_stream = df.writeStream
        
        match = re.search(r'/([^/]+)$', streaming_query_info.query_name)
        table_name = ''
        if match:
            table_name = match.group(1)
        self.spark.sparkContext.setJobGroup(
            groupId=f"{self.__class__.__module__}.{self.__class__.__qualname__}.{table_name}",
            description=f"Streaming QueryName: {streaming_query_info.query_name}"
        )
        return (
            write_stream
                .trigger(availableNow=True)
                .option(
                    GlobalConstants.CHECKPOINT_LOCATION_OPTION_NAME,
                    streaming_query_info.checkpoint_path,
                )
                .foreachBatch(lambda df, batch_id: streaming_query_info.batch_fn(df, batch_id))
                .queryName(streaming_query_info.query_name)
                .start()
        )
