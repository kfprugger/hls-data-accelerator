from common.exceptions.base_dtt_common_exception import BaseDttCommonCustomException


class BaseColumnExpressionBuilderException(BaseDttCommonCustomException):
    """Base class for custom exceptions in ColumnExpressionBuilder."""
    pass


class SourceFieldNameMustBeNonEmptyException(BaseColumnExpressionBuilderException):
    """Exception raised when source field name is None."""
    pass


class ColumnAlreadyExistsException(BaseColumnExpressionBuilderException):
    """Exception raised when column already exists in DataFrame."""
    pass
