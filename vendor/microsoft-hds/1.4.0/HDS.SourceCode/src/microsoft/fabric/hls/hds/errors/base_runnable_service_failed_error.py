class BaseRunnableServiceFailedError(Exception):
    """Exception raised for errors when BaseRunnableService execution fails.

    Attributes:
        message -- explanation of the error
    """

    def __init__(self, message="Execution metrics failed."):
        self.message = message
        super().__init__(self.message)