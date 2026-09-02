class FlattenFailedError(Exception):
    """Exception raised for errors when flattening fails.

    Attributes:
        message -- explanation of the error
    """

    def __init__(self, message="Flattening failed."):
        self.message = message
        super().__init__(self.message)