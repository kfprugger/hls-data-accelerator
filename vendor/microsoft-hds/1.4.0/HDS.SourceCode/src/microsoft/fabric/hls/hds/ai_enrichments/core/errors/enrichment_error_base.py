# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------

class EnrichmentErrorBase(Exception):
    """
    Represents an exception for enrichment errors.

    Attributes:
        message: A descriptive error message.
    """

    def __init__(self, message: str):
        """
        Initializes the exception with a specified error message.

        Args:
            message: The error message.
        """
        self.message = message
        super().__init__(message)