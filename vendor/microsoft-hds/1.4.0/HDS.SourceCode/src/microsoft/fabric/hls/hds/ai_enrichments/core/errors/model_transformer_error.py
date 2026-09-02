# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------

# Import the base class for enrichment errors
from microsoft.fabric.hls.hds.ai_enrichments.core.errors.enrichment_error_base import EnrichmentErrorBase

class ModelTransformerError(EnrichmentErrorBase):
    """
    Custom exception class that extends the EnrichmentErrorBase
    to handle errors within the model transformation process.
    """

    def __init__(self, message: str):
        """
        Initialize the ModelTransformerError with a descriptive message.

        Args:
            message (str): The error message explaining the nature of the error.
        """
        super().__init__(message)
