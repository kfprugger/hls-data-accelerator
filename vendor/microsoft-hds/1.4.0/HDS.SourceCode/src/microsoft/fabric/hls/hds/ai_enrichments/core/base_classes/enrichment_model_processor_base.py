# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List

from microsoft.fabric.hls.hds.ai_enrichments.core.base_classes.enrichment_model_client_base import (
    EnrichmentModelClientBase,
)
from microsoft.fabric.hls.hds.ai_enrichments.core.clients.client_retry_management.retry_client_manager import (
    RetryClientManager,
)
from microsoft.fabric.hls.hds.ai_enrichments.core.clients.default_enrichment_model_client_orchestrator import (
    DefaultEnrichmentModelClientOrchestrator,
)
from microsoft.fabric.hls.hds.ai_enrichments.core.clients.models.enrichment_api_response import (
    EnrichmentAPIResponse,
)
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_context import (
    EnrichmentContext,
)
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_response import (
    EnrichmentResponse,
)
from microsoft.fabric.hls.hds.ai_enrichments.core.utils.ai_enrichments_utils import (
    AIEnrichmentsUtils,
)
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_constants import (
    AIEnrichmentsConstants as EC,
)


class EnrichmentModelProcessorBase(ABC):
    """
    Abstract base class for executing enrichment models concurrently.
    Subclasses must implement post_process_api_responses to transform
    API responses into final enrichment objects. They can optionally
    override pre_process_input_batch if needed.
    """

    def __init__(
        self,
        get_model_client: Callable[[Dict], EnrichmentModelClientBase] = lambda model_config: (
            EnrichmentModelProcessorBase.get_default_model_client(model_config)
        ),
        max_workers: int = EC.DEFAULT_AI_ENRICHMENT_EXECUTION_THREADS,
        execution_batch_size: int = EC.DEFAULT_AI_ENRICHMENT_EXECUTION_BATCH_SIZE,
    ) -> None:
        """
        Initialize concurrency limits and the callable for obtaining a model client.

        Args:
            get_model_client (Callable[[Dict], EnrichmentModelClientBase]):
                Function to return a configured model client.
            max_workers (int): Maximum worker threads for parallel processing.
            execution_batch_size (int): Number of items to process in each parallel batch.
        """
        self._max_workers = max_workers if max_workers > 0 else EC.DEFAULT_AI_ENRICHMENT_EXECUTION_THREADS
        self._execution_batch_size = (
            execution_batch_size
            if execution_batch_size > 0
            else EC.DEFAULT_AI_ENRICHMENT_EXECUTION_BATCH_SIZE
        )
        self.get_model_client = get_model_client

    @abstractmethod
    def post_process_api_responses(
        self,
        enrichment_generation_id: str,
        document_inputs: List[str],
        results: List[EnrichmentAPIResponse]
    ) -> List[EnrichmentResponse]:
        """
        Convert API responses into EnrichmentResponse objects. Must be implemented by subclasses.

        Args:
            enrichment_generation_id (str): Unique identifier for this enrichment run.
            document_inputs (List[str]): Original inputs sent to the model.
            results (List[EnrichmentAPIResponse]): Raw model responses.

        Returns:
            List[EnrichmentResponse]: Processed results from the model API.
        """

    def pre_process_input_batch(
        self,
        document_inputs: List[EnrichmentContext],
    ) -> List[str]:
        """
        Extract text content from the provided EnrichmentContext objects.

        Args:
            document_inputs (List[EnrichmentContext]): List of contexts containing file references.

        Returns:
            List[str]: Text contents extracted for downstream processing.
        """
        return AIEnrichmentsUtils.get_content_from_file_references(document_inputs)

    def process(
        self,
        enrichment_id: str,
        model_config: Dict,
        input_data: List[EnrichmentContext]
    ) -> List[EnrichmentResponse]:
        """
        Orchestrate parallel processing of the provided input data.

        Args:
            enrichment_id (str): Unique identifier for tracking the enrichment job.
            model_config (Dict): Configuration details for model connectivity.
            input_data (List[str]): Data items to enrich.
            save_raw_response (bool): Flag to determine if raw responses should be saved.
            output_dir (str): Directory to write results.

        Returns:
            List[EnrichmentResponse]: Collection of enrichment results.
        """
       
        self._client_manager = RetryClientManager(self.get_model_client(model_config))
        enrichment_responses: List[EnrichmentResponse] = []

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            futures = []
            for i in range(0, len(input_data), self._execution_batch_size):
                futures.append(
                    executor.submit(
                        self._process_batch,
                        enrichment_id,
                        input_data,
                        i
                    )
                )

            for future in as_completed(futures):
                enrichment_responses.extend(future.result())

        return enrichment_responses

    def _process_batch(
        self,
        enrichment_generation_id: str,
        inputs: List[EnrichmentContext],
        start_index: int
    ) -> List[EnrichmentResponse]:
        """
        Handle a chunk of inputs, from converting them to model format 
        to sending them through the model client and post-processing results.
        """
        # Identify how many items to process in this batch        
        batch_size = min(self._execution_batch_size, len(inputs) - start_index)
        input_batch = inputs[start_index : start_index + batch_size]

        # Obtain client executor that manages retries
        client_executor = self._client_manager.get_client_executor()

        # Convert raw model responses into EnrichmentResponse objects
        return  self.post_process_api_responses(
            enrichment_generation_id,
            input_batch,
             client_executor(self.pre_process_input_batch(input_batch))
        )

    @staticmethod
    def get_default_model_client(model_config: dict
    ) -> DefaultEnrichmentModelClientOrchestrator:
        """
        Returns an instance of the DefaultEnrichmentModelClientOrchestrator
        using the provided Spark session, configuration, and logger.

        Args:
            spark (SparkSession): Spark session instance.
            model_config (dict): Configuration for the model (endpoint, key, etc.).

        Returns:
            DefaultEnrichmentModelClientOrchestrator: A default model client orchestrator.
        """
        # Extract model endpoint and key from configuration
        api_endpoint = model_config.get("api_endpoint")
        api_key = model_config.get("api_key")

        # Create the orchestrator using the extracted configuration
        return DefaultEnrichmentModelClientOrchestrator(
            api_endpoint=api_endpoint,
            api_key=api_key
        )