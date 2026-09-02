from microsoft.fabric.hls.hds.errors.base_runnable_service_failed_error import BaseRunnableServiceFailedError

class ClaimsCCLFIngestionFailedError(BaseRunnableServiceFailedError):
    """Exception raised for errors when flattening fails.

    Attributes:
        message -- explanation of the error
    """

    def __init__(self, message="Bronze Ingestion Failed.", exceptions=None):
        self.message = message
        self.exceptions = exceptions if exceptions else []
        
        if len(self.exceptions) > 0:
            exception_messages = "\n\n".join([f"- {type(e).__name__}: {str(e)}" for e in self.exceptions])
            self.message += f"\nCaused by {len(self.exceptions)} exception(s):\n{exception_messages}"
        
        super().__init__(self.message)