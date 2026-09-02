# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
from functools import partial
import json
from typing import Dict
from pyspark.sql import DataFrame, SparkSession
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.structured_stream.file_stream_reader import FileStreamReader
from microsoft.fabric.hls.hds.structured_stream.stream_orchestrator import StreamOrchestrator, StreamingQueryInfo
from microsoft.fabric.hls.hds.utils.dataframe_utils import append_to_delta_table_using_path
from microsoft.fabric.hls.hds.utils.logging_helper import LoggingHelper
from microsoft.fabric.hls.hds.utils.utils import Utils


class VocabularyIngestionService:
    def __init__(
        self,
        spark: SparkSession,
        target_tables_path: str,
        vocabulary_path: str,
        checkpoint_path: str,
        **kwargs
    ):
        """Ingest vocabulary data into target tables

        Args:
            - spark (SparkSession): Spark Session
            - target_tables_path (str): The absolute abfss URL of the tables location
            - vocabulary_path (str): The path where vocab is located
            - checkpoint_path (str): The path where the checkpoint information for spark structured streaming is stored
            - **kwargs (dict): An optional dictionary that customer can use to configure the vocabulary ingestion service
                - run_id (str): The run_id for the run. If none is provided, one will be generated
        """
        self.spark = spark
        self.target_tables_path = target_tables_path
        self.vocabulary_path = vocabulary_path
        self.checkpoint_path = checkpoint_path
        self._logger = LoggingHelper.get_generic_logger(
            self.spark, self.__class__.__name__, GlobalConstants.LOGGING_LEVEL
        )

    def ingest_vocab_data(self, vocab_schema: Dict, **kwargs):
        """Set up spark structured streaming on the vocab data

        Args:
            vocab_schema (Dict): The key is the table_name (str) and the value is the schema of the table
            **kwargs (dict): An optional dictionary that customer can use to configure the vocabulary ingestion service
                - collect_metrics_fn (function, optional): A function that collects metrics.
        """
        self._logger.info(f"{LC.VOCAB_INGESTION_START_INFO_MSG}")
        
        self.collect_metrics_fn = kwargs.get("collect_metrics_fn", None)
        
        file_stream_reader = FileStreamReader(self.spark)    
        stream_orchestrator = StreamOrchestrator(self.spark, max_structured_streaming_queries=None)

        for table_name, schema in vocab_schema.items():
            streaming_path = f"{self.vocabulary_path}/*{table_name}.csv"

            # If there is no data in the streaming, do nothing
            if not Utils.is_files_in_path(spark=self.spark, path=streaming_path):
                self._logger.info(
                    f"{LC.STREAMING_PATH_DOES_NOT_EXIST_INFO_MSG.format(streaming_path=streaming_path)}"
                )
            else:
                self._logger.info(
                    f"{LC.SET_STRUCTURED_STREAMING_INFO_MSG.format(streaming_path)}"
                )
                
                streaming_df = file_stream_reader.set_up_streaming_csv(schema, streaming_path)
                
                batch_fn = partial(
                    self._process_vocab_data,
                    table_name=table_name)
                
                streaming_query_info = StreamingQueryInfo(
                    query_name = f"{ self.__class__.__name__}.{table_name}",
                    checkpoint_path = f"{self.checkpoint_path}/{table_name}",
                    streaming_dataframe=streaming_df,
                    batch_fn=batch_fn,
                    data_format="delta")
                
                stream_orchestrator.enqueue_streaming_query(streaming_query_info)

        # Block until all queries have completed streaming
        streaming_exception = None
        try:
            stream_orchestrator.await_all()
        except Exception as ex:
            streaming_exception = ex

        streaming_metrics = stream_orchestrator.get_streaming_metrics()
        self._logger.info(f"Streaming metrics: {json.dumps(streaming_metrics, indent=2)}")
        
        if streaming_exception:
            self._logger.error(LC.STREAMING_FAILED_ERROR_MSG.format(streaming_exception))
            raise streaming_exception

        self._logger.info(f"{LC.VOCAB_INGESTION_COMPLETED_INFO_MSG}")
        
    def _process_vocab_data(self, df: DataFrame, batchid: int, table_name: str, **kwargs):
        """Process the vocab data

        Args:
            df (DataFrame): The dataframe to process
            batchid (int): The batch id
            table_name (str): The table name to ingest the data
        """
        # append dataframe to delta table
        append_to_delta_table_using_path(
            df_to_process=df,
            delta_table_path=f"{self.target_tables_path}/{table_name.lower()}",
            logger=self._logger,
            collect_metrics_fn=self.collect_metrics_fn,
        )
