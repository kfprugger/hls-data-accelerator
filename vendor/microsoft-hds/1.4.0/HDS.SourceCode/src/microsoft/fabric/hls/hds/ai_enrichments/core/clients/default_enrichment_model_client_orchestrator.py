import requests
from typing import Any, List
from microsoft.fabric.hls.hds.ai_enrichments.core.base_classes.enrichment_model_client_base import EnrichmentModelClientBase

class DefaultEnrichmentModelClientOrchestrator(EnrichmentModelClientBase):
    """
    Provides functionality for making POST requests to an enrichment API endpoint.
    """

    def __init__(
        self, 
        api_endpoint: str, 
        api_key: str, 
        **kwargs
    ) -> None:
        """
        Initializes the client with endpoint, key, and logger.

        :param api_endpoint: API endpoint URL.
        :param api_key: API key for authentication.
        :param logger: Logger instance for logging.
        :param kwargs: Additional keyword arguments.
        """
        super().__init__(api_endpoint, api_key, **kwargs)

    def execute(self, model_inputs: List[str] = None) -> List[Any]:
        """
        Sends POST requests for each input in model_inputs.

        :param model_inputs: List of string payloads for the request body.
        :return: List of responses, parsed if JSON is detected.
        :raises: RequestException if any request fails.
        """
        if model_inputs is None:
            model_inputs = []

        headers = self.get_headers()
        responses = []

        for input_data in model_inputs:
            try:
                response = requests.request(
                    method="POST",
                    url=self.api_endpoint,
                    headers=headers,
                    data=input_data
                )
                response.raise_for_status()
                if response.headers.get("Content-Type") == "application/json":
                    responses.append(response.json())
                else:
                    responses.append(response.text)
            except requests.exceptions.RequestException as e:
                raise

        return responses
