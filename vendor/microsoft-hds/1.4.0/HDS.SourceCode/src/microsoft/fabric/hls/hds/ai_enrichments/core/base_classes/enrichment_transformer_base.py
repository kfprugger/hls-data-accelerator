# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_constants import (
    AIEnrichmentsConstants as EC,
)
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_logging_constants import (
    AIEnrichmentsLoggingConstants as ELC,
)
from microsoft.fabric.hls.hds.ai_enrichments.core.errors.model_transformer_error import (
    ModelTransformerError,
)
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_context import (
    EnrichmentContext,
)
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_response import (
    EnrichmentResponse,
)
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_result import (
    EnrichmentResult,
)


class EnrichmentTransformerBase(ABC):
    """
    An abstract base class defining a contract for transforming raw model output
    into enrichment results. Subclasses must implement build_enrichment_result
    to parse the response and construct an EnrichmentResult object.
    """

    def __init__(self, max_workers: int = EC.DEFAULT_AI_ENRICHMENT_EXECUTION_THREADS) -> None:
        """
        Initialize the transformer.
        
        Args:
            max_workers (int): Maximum number of threads to use for parallel processing.
        """
        self._max_workers = max_workers

    @abstractmethod
    def build_enrichment_result(
        self,
        enrichment_generation_id: str,
        enrichment_context: EnrichmentContext,
        response: EnrichmentResponse
    ) -> EnrichmentResult:
        """
        Build an enrichment result object from the provided context and raw model response.
        
        Args:
            enrichment_generation_id (str): Unique ID for this enrichment generation.
            enrichment_context (EnrichmentContext): Context containing additional information.
            response (EnrichmentResponse): Raw response from the model.
        
        Returns:
            EnrichmentResult: A fully populated enrichment result object.
        """
        raise NotImplementedError(ELC.AI_ENRICHMENT_MODEL_EXECUTION_IMPLEMENTATION_ERROR)

    def transform(
        self,
        enrichment_generation_id: str,
        enrichment_contexts: List[EnrichmentContext],
        raw_response_data: List[Dict[str, Any]],
    ) -> List[EnrichmentResult]:
        """
        Transform raw response data into a list of EnrichmentResult objects, using
        a thread pool for parallel processing.

        Args:
            enrichment_generation_id (str): Unique ID for this enrichment generation.
            enrichment_contexts (List[EnrichmentContext]): List of contexts needed for transformation.
            raw_response_data (List[Dict[str, Any]]): List of raw responses from the model.

        Returns:
            List[EnrichmentResult]: A list of processed enrichment results.
        """

        def _process_enrichment_response(
            context: Optional[EnrichmentContext],
            response: Dict[str, Any]
        ) -> Optional[EnrichmentResult]:
            """
            Helper function to process a single model response and context,
            returning an EnrichmentResult if valid.
            """
            if not context:
                return None

            return self.build_enrichment_result(
                enrichment_generation_id,
                context,
                response,
            )

        results: List[EnrichmentResult] = []

        try:
            with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
                futures = {
                    executor.submit(_process_enrichment_response, ctx, resp): resp
                    for resp, ctx in zip(raw_response_data, enrichment_contexts)
                }
                for future in as_completed(futures):
                    try:
                        result = future.result()
                        if result:
                            results.append(result)
                    except Exception as exc:
                        raise ModelTransformerError(
                            EC.ENRICHMENT_UNEXPECTED_ERROR.format(method="transform", error=exc)
                        ) from exc

            return results
        except Exception as exc:
            raise ModelTransformerError(
                EC.ENRICHMENT_UNEXPECTED_ERROR.format(method="transform", error=exc)
            ) from exc
