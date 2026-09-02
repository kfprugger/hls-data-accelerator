from common.exceptions.processor.steps.base_processing_step_exception import BaseProcessingStepException


class ColumnSelectorBase(BaseProcessingStepException):
    """Base class for custom exceptions in ColumnSelector."""
    pass


class SourceFieldNameMustBeNonEmptyException(ColumnSelectorBase):
    """Exception raised when source field name is None."""
    pass
