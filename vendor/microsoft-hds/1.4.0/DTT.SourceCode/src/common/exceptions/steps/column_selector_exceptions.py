from common.exceptions.base_dtt_common_exception import BaseDttCommonCustomException


class ColumnSelectorBase(BaseDttCommonCustomException):
    """Base class for custom exceptions in ColumnSelector."""
    pass


class SourceFieldNameMustBeNonEmptyException(ColumnSelectorBase):
    """Exception raised when source field name is None."""
    pass
