from common.exceptions.processor.steps.base_processing_step_exception import BaseProcessingStepException


class BaseColumnExpressionBuilderException(BaseProcessingStepException):
    """Base class for custom exceptions in ColumnExpressionBuilder."""
    pass


class SourceFieldNameMustBeNonEmptyException(BaseColumnExpressionBuilderException):
    """Exception raised when source field name is None."""
    pass


class ColumnAlreadyExistsException(BaseColumnExpressionBuilderException):
    """Exception raised when column already exists in DataFrame."""
    pass
