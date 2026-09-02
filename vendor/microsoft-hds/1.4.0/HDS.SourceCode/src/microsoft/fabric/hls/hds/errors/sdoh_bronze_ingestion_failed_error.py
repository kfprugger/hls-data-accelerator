from microsoft.fabric.hls.hds.errors.base_runnable_service_failed_error import BaseRunnableServiceFailedError

class SDOHBronzeIngestionFailedError(BaseRunnableServiceFailedError):
    """Exception raised for errors when SDOH Bronze ingestion fails."""

    def __init__(self, message="SDOH Bronze Ingestion Failed.", exceptions=None):
        self.message = message
        super().__init__(self.message)