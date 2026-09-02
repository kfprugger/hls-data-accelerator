# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------

# Import the base class for enrichment errors
from microsoft.fabric.hls.hds.ai_enrichments.core.errors.enrichment_error_base import EnrichmentErrorBase

class ModelProcessError(EnrichmentErrorBase):
    """
    Custom exception class for enrichment service errors.

    Attributes:
        message (str): The error message to be displayed.
    """
    def __init__(self, message: str):
        """
        Initializes the ModelProcessError with a message 

        Args:
            message (str): The error message to be displayed.
        """
        # Call the parent constructor with the provided message
        super().__init__(message)
