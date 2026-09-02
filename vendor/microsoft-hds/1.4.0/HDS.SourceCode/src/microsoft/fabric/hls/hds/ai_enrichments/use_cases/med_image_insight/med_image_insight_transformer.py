# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------

from typing import Any, Dict, List
from microsoft.fabric.hls.hds.ai_enrichments.core.base_classes.enrichment_transformer_base import EnrichmentTransformerBase
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_constants import AIEnrichmentsConstants as EC
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_logging_constants import AIEnrichmentsLoggingConstants as ELC
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_context import EnrichmentContext
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_output import EnrichmentOutput
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_response import EnrichmentResponse
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_result import EnrichmentResult
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.types.embedding_output import EmbeddingOutput

class MedImageInsightTransformer(EnrichmentTransformerBase):
    """
    Responsible for transforming raw MedImageInsights model output into
    domain-specific enrichment results.
    """

    def __init__(
        self,
        max_workers: int = EC.DEFAULT_AI_ENRICHMENT_EXECUTION_THREADS
    ) -> None:
        """
        Initialize the transformer with Spark session and optional MSSparkUtils client.
        """
        super().__init__(
            max_workers=max_workers
        )

    def build_enrichment_result(
        self,
        enrichment_generation_id: str,
        enrichment_context: EnrichmentContext,
        response: EnrichmentResponse,
    ) -> EnrichmentResult:
        """
        Build the enrichment result from the MedImageInsights response.

        Args:
            enrichment_generation_id: Unique ID for this enrichment cycle.
            enrichment_context: Context of the enrichment process.
            response: Response object containing model output.

        Returns:
            An EnrichmentResult containing structured outputs.
        """
        outputs: List[EnrichmentOutput] = []
        self._transform_embedding_response(response.content, outputs)
        return EnrichmentResult(
            context=enrichment_context,
            outputs=outputs,
            enrichment_generation_id=enrichment_generation_id,
        )


    def _transform_embedding_response(
        self, item: Dict[str, Any], outputs: List[EnrichmentOutput]
    ) -> None:
        """
        Process embedding-related data and append it to the outputs list.

        Args:
            item: Response content from the enrichment process.
            outputs: List for storing EnrichmentOutput objects.
        """
        try:
            if isinstance(item, list):
                for entity in item:
                    if isinstance(entity, dict):
                        embedding_output = self._create_embedding_output(entity)
                        outputs.append(
                            EnrichmentOutput(type="embedding", value=embedding_output)
                        )
            else:
                print(
                    ELC.MED_IMAGE_INSIGHT_OUTPUT_RESPONSE_WARNING.format(response=item)
                )
        except Exception as e:
           print(EC.ENRICHMENT_UNEXPECTED_ERROR.format(method="_transform_embedding_response", error=e))


    def _create_embedding_output(self, entity: Dict[str, Any]) -> EmbeddingOutput:
        """
        Construct an EmbeddingOutput object from the given entity.

        Args:
            entity: Dictionary holding embedding data.

        Returns:
            An EmbeddingOutput with the extracted vector.
        """
        image_features = entity.get("image_features", [])
        if any(isinstance(i, list) for i in image_features):
            image_features = [float(val) for sublist in image_features for val in sublist]
        else:
            image_features = [float(val) for val in image_features]

        return EmbeddingOutput(vector=image_features)
