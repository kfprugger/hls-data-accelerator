from enum import Enum
from dataclasses import dataclass
from microsoft.fabric.hls.hds.data_models.execution_metadata import ExecutionMetadata

# Define Enum for execution status
class InternalExecutionStatus(Enum):
    SUCCEEDED = "Succeeded"
    SUCCEEDED_WITH_ERRORS = "SucceededWithErrors"
    FAILED = "Failed"
    FAILED_WITH_REMOTE = "FailedWithRemote"
    CANCELLED = "Cancelled"
    PENDING = "Pending"

class ExecutionStatus(Enum):
    SUCCEEDED = "Succeeded"
    FAILED = "Failed"
    PENDING = "Pending"
    FAILED_WITH_VALIDATION_ERRORS = "FailedWithValidationErrors"
    SUCCEEDED_WITH_VALIDATION_WARNINGS = "SucceededWithValidationWarnings"

# Define a dataclass for the return type
@dataclass
class ExecutionResult:
    internalExecutionStatus: InternalExecutionStatus | None # Internal status of the execution
    internalExecutionStatusDetails: str | None # Additional information or error message
    executionStatus: ExecutionStatus | None # Customer facing status of the execution
    executionStatusDetails: str | None # Additional information or error message
    executionMetadata: ExecutionMetadata | None # Metadata of the execution

    