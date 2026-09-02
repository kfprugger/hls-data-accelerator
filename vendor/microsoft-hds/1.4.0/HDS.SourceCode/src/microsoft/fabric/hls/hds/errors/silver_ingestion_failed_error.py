from microsoft.fabric.hls.hds.errors.base_runnable_service_failed_error import BaseRunnableServiceFailedError

class SilverIngestionFailedError(BaseRunnableServiceFailedError):
    """Exception raised for errors when Silver Ingestion Service fails.

    Attributes:
        message -- explanation of the error
    """

    def __init__(self, message="Silver Ingestion Failed."):
        self.message = message
        super().__init__(self.message)