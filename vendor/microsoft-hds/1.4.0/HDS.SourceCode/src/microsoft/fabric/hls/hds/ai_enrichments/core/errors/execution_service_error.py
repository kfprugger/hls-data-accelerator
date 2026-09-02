# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------

from microsoft.fabric.hls.hds.ai_enrichments.core.errors.enrichment_error_base import EnrichmentErrorBase

class ExecutionServiceError(EnrichmentErrorBase):
    """
    Represents errors encountered during the enrichment execution process.

    Attributes:
        message (str): The error message.
    """

    def __init__(self, message: str):
        """
        Initialize the ExecutionServiceError with a message.

        Args:
            message (str): The error message to be displayed.
        """
        # Call the base class initializer to store the message
        super().__init__(message)
