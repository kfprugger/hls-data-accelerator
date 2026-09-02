# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------
from typing import Any
from abc import ABC, abstractmethod
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_logging_constants import AIEnrichmentsLoggingConstants as LC

class EnrichmentModelClientBase(ABC):
    """
    Abstract base client for making API calls for enrichment models.
    This class defines the structure for interacting with enrichment model APIs,
    handling setup tasks like logging and header generation.
    """

    def __init__(self, api_endpoint: str, api_key: str, **kwargs):
        """
        Initialize the client with endpoint, key, logger, and any extra attributes.

        Args:
            api_endpoint (str): The API endpoint URL.
            api_key (str): The authentication key.
            kwargs: Additional key-value attributes.
        """
        self.api_endpoint = api_endpoint     
        self.api_key = api_key                          
        
        # Dynamically set extra attributes
        for k, v in kwargs.items():
            setattr(self, k, v)

    @abstractmethod
    def execute(self, method: str = "POST", **kwargs) -> Any:
        """
        Abstract method to send the request to the API using the specified HTTP method.

        Args:
            method (str): HTTP method (default "POST").
            kwargs: Request parameters.
        """
        raise NotImplementedError()

    def get_headers(self) -> dict:
        """
        Generate default headers for API calls, including authorization.

        Returns:
            dict: Dictionary of default HTTP headers.
        """
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
