class ValidationFailedError(Exception):
    """Exception raised for errors when flattening fails.

    Attributes:
        message -- explanation of the error
    """

    def __init__(self, message="Validation Failed."):
        self.message = message
        super().__init__(self.message)