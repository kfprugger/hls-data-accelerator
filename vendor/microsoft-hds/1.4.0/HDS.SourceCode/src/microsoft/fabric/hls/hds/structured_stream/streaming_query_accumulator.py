import json
from pyspark.sql.streaming.listener import StreamingQueryListener, QueryProgressEvent, QueryStartedEvent, QueryTerminatedEvent
from microsoft.fabric.hls.hds.utils.data_manager_logger import DataManagerLogger

PROCESSED_ROWS = "processed_rows"
STARTED = "started"
IN_PROGRESS = "In Progress"
FAILED = "Failed"
SUCCEEDED = "Succeeded"

class StreamingQueryAccumulator(StreamingQueryListener):

    def __init__(self, logger: DataManagerLogger):
        self.streaming_data = {}
        self._logger = logger
    
    def get_streaming_data(self) -> dict:
        return self.streaming_data
    
    def onQueryStarted(self, event: QueryStartedEvent) -> None:
        stream_id = str(event.id)
        run_id = str(event.runId)
        self._logger.info(f"Streaming query started with Id: {stream_id}, runId: {run_id}, name: {event.name}")
        try:
            if stream_id not in self.streaming_data:
                self.streaming_data[run_id] = {
                    "state": STARTED,
                    "name": event.name,
                    "stream_id": stream_id,
                    PROCESSED_ROWS: 0
                }
        except Exception as ex:
            self._logger.error(f"Error occurred during onQueryStarted: {str(ex)}")

    def onQueryProgress(self, event: QueryProgressEvent) -> None:
        stream_id = str(event.progress.id)
        run_id = str(event.progress.runId)
        
        progress = {
            "id" : stream_id,
            "runId" : run_id,
            "name" : event.progress.name,
            "timestamp" : event.progress.timestamp,
            "batchId" : event.progress.batchId,
            "numInputRows" : event.progress.numInputRows,
            "inputRowsPerSecond" : event.progress.inputRowsPerSecond,
            "processedRowsPerSecond" : event.progress.processedRowsPerSecond,
            "durationMs": event.progress.durationMs
        }
        
        self._logger.info(f"Streaming query progress: {progress}")
        try:
            if run_id not in self.streaming_data or PROCESSED_ROWS not in self.streaming_data[run_id]:
                self.streaming_data[run_id] = {
                    PROCESSED_ROWS: 0,
                }
            
            self.streaming_data[run_id] = {
                "state": IN_PROGRESS,
                "stream_id": stream_id,
                PROCESSED_ROWS: self.streaming_data[run_id][PROCESSED_ROWS] + int(event.progress.numInputRows),
                "last_batch_id": event.progress.batchId
            }
        except Exception as ex:
            self._logger.error(f"Error occurred during onQueryProgress: {ex}")

    def onQueryIdle(self, event: any) -> None:
        try:
            self._logger.info(f"Streaming query idle with event data: {json.dumps(event)}")
        except Exception as ex:
            self._logger.error(f"Error occurred during onQueryIdle: {str(ex)}")

    def onQueryTerminated(self, event: QueryTerminatedEvent) -> None:
        stream_id = str(event.id)
        run_id = str(event.runId)
        self._logger.info(f"Streaming query terminated with id: {stream_id} and runId: {run_id}")
        try:
            if run_id not in self.streaming_data:
                self.streaming_data[run_id] = {
                    "stream_id" : stream_id
                }
            
            self.streaming_data[run_id]["state"] = SUCCEEDED if (event.exception is None or event.exception == "") else FAILED
            self.streaming_data[run_id]["exception"] = event.exception if event.exception else ""
        except Exception as ex:
            self._logger.error(f"Error occurred during onQueryTerminated: {str(ex)}")