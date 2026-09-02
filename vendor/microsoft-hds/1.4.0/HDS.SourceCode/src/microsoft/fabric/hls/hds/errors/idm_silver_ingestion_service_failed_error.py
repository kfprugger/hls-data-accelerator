from microsoft.fabric.hls.hds.errors.base_runnable_service_failed_error import BaseRunnableServiceFailedError

class IDMSilverIngestionFailedError(BaseRunnableServiceFailedError):
    """Exception raised for errors during IDM Silver ingestion.

    Attributes:
        message -- explanation of the error
        exceptions -- list of underlying exceptions (if any)
    """

    def __init__(self, message="IDM Silver Ingestion Failed.", exceptions=None):
        self.message = message
        self.exceptions = exceptions if exceptions else []

        if len(self.exceptions) > 0:
            exception_messages = "\n\n".join([f"- {type(e).__name__}: {str(e)}" for e in self.exceptions])
            self.message += f"\nCaused by {len(self.exceptions)} exception(s):\n{exception_messages}" 

        super().__init__(self.message)
