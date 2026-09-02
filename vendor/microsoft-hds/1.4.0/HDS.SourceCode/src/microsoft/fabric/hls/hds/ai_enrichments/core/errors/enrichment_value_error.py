# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
from microsoft.fabric.hls.hds.ai_enrichments.core.errors.enrichment_error_base import EnrichmentErrorBase

class EnrichmentValueError(EnrichmentErrorBase):
    """
    Custom exception class for enrichment service errors.

    This error is raised when an invalid value is encountered during the
    enrichment process. It inherits from EnrichmentErrorBase for consistent
    error handling.

    Attributes:
        message (str): The error message to be displayed.
    """

    def __init__(self, message: str):
        """
        Initializes the EnrichmentValueError with a message.

        Args:
            message (str): A description of the error that occurred.
        """
        # Call the base class constructor to set up the error message
        super().__init__(message)
