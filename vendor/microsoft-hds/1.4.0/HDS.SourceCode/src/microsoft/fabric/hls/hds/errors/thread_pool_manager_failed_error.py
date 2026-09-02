class ThreadPoolManagerFailedError(Exception):
    """Exception raised for when one or more streaming queries fail.

    Attributes:
        message -- explanation of the error
    """

    def __init__(self, message="Thread Pool Manager Failed."):
        self.message = message
        super().__init__(self.message)