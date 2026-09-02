# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------
from typing import List
from azure.ai.textanalytics import TextAnalyticsClient
from azure.core.credentials import AzureKeyCredential
from microsoft.fabric.hls.hds.ai_enrichments.core.base_classes.enrichment_model_client_base import EnrichmentModelClientBase
from microsoft.fabric.hls.hds.ai_enrichments.core.clients.models.enrichment_api_response import EnrichmentAPIResponse
from microsoft.fabric.hls.hds.ai_enrichments.core.errors.model_configuration_error import ModelConfigurationError
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_logging_constants import AIEnrichmentsLoggingConstants as AIE

class TA4hClientOrchestrator(EnrichmentModelClientBase):
    """
    Orchestrator class for interacting with the Azure Text Analytics for Health (TA4H) service.
    """

    def __init__(self, api_endpoint: str, api_key: str, **kwargs):
        """
        Initialize the orchestrator with service endpoint and credentials.

        Args:
            api_endpoint (str): The API endpoint URL.
            api_key (str): The authentication key.
            kwargs: Additional key-value attributes.
        """
        super().__init__(api_endpoint, api_key, **kwargs)
        self._create_client()

    def _create_client(self):
        """
        Create the Text Analytics client.
        """
        try:
            self.client = TextAnalyticsClient(
                endpoint=self.api_endpoint,
                credential=AzureKeyCredential(self.api_key)
            )
        except Exception as e:
            raise ModelConfigurationError(e)

    def execute(self, documents: List[str]) -> List[EnrichmentAPIResponse]:
        """
        Run the enrichment process for the provided documents.

        Args:
            documents (List[str]): List of documents to be processed.

        Returns:
            List[EnrichmentAPIResponse]: List of enrichment API responses.
        """
        try:
           
            analyze_params = {"documents": documents}
            if self.fhir_version is not None:
                analyze_params["fhir_version"] = self.fhir_version
            if self.model_version is not None:
                analyze_params["model_version"] = self.model_version
            

            # Call the Text Analytics API for healthcare entity recognition
            results = self.client.begin_analyze_healthcare_entities(**analyze_params).result()
            
            return self._process_results(results, len(documents))
        except Exception as e:
            return [EnrichmentAPIResponse(error_message=str(e)) for _ in range(len(documents))]

    def _process_results(self, results, num_documents: int) -> List[EnrichmentAPIResponse]:
        """
        Process the results from the Text Analytics client.

        Args:
            results: The results from the Text Analytics client.
            num_documents (int): The number of documents processed.

        Returns:
            List[EnrichmentAPIResponse]: List of enrichment API responses.
        """
        responses = [EnrichmentAPIResponse() for _ in range(num_documents)]
        for doc in results:
            if doc.is_error:
                responses[int(doc.id)] = EnrichmentAPIResponse(error_message=doc.error.message)
            else:
                responses[int(doc.id)] = EnrichmentAPIResponse(data=doc)
        return responses

