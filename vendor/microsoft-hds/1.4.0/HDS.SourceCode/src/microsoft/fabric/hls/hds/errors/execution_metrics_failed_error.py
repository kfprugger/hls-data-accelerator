class ExecutionMetricsFailedError(Exception):
    """Exception raised for errors when execution metrics instrumentation fails.

    Attributes:
        message -- explanation of the error
    """

    def __init__(self, message="Execution metrics failed."):
        self.message = message
        super().__init__(self.message)