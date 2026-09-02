# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------

from microsoft.fabric.hls.hds.ai_enrichments.core.errors.enrichment_error_base import EnrichmentErrorBase


class ModelConfigurationError(EnrichmentErrorBase):
    """
    Exception raised for model configuration issues in the enrichment service.

    Attributes:
        message (str): Description of the error.
    """
    def __init__(self, message: str):
        """
        Initializes the error with a descriptive message.

        Args:
            message (str): Description of the error.
        """
        super().__init__(message)
