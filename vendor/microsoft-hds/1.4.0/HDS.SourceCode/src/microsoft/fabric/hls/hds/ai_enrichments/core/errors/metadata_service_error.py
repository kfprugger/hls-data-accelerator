# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------

from microsoft.fabric.hls.hds.ai_enrichments.core.errors.enrichment_error_base import EnrichmentErrorBase

class MetaDataServiceError(EnrichmentErrorBase):
    """
    Exception raised for metadata service errors.

    Attributes:
        message (str): A descriptive error message.
    """

    def __init__(self, message: str):
        """
        Initialize the MetaDataServiceError.

        Args:
            message (str): The error message.
        """
        super().__init__(message)
