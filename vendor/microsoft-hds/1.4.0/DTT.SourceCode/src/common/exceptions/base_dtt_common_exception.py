class BaseDttCommonCustomException(Exception):
    """Base class for custom exceptions in the DTT common module."""
    def __init__(self, message, **context):
        super().__init__(message)
        self.context = context

    def __str__(self):
        context = (
            "\n".join([f"{key}: {value}" for key, value in self.context.items()])
            if self.context
            else "no context"
        )
        return f"{super().__str__()}\n{context}"
