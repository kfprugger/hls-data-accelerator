# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------

from typing import Any, Dict, List, Optional
from pyspark.sql import SparkSession
from microsoft.fabric.hls.hds.ai_enrichments.core.base_classes.enrichment_transformer_base import EnrichmentTransformerBase
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_constants import AIEnrichmentsConstants as EC
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_logging_constants import AIEnrichmentsLoggingConstants as ELC
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_context import EnrichmentContext
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_output import EnrichmentOutput
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_response import EnrichmentResponse
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_result import EnrichmentResult
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.types.segmentation.segmentation_mask import SegmentationMask
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.types.segmentation_2d_output import Segmentation2DOutput
from microsoft.fabric.hls.hds.ai_enrichments.use_cases.common.utils.enrichment_model_utils import EnrichmentModelUtils as ModelUtils



class MedImageParseTransformer(EnrichmentTransformerBase):
    """
    Transforms raw medical imaging data into enriched segmentation results.
    """

    def __init__(
        self,
        max_workers: int = EC.DEFAULT_AI_ENRICHMENT_EXECUTION_THREADS
    ) -> None:
        """
        Initialize with Spark session and optional MSSparkUtils client.
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
        Build the EnrichmentResult with segmentation outputs.
        """
        outputs: List[EnrichmentOutput] = []
        self._transform_segmentation_response(response.content, outputs)
        return EnrichmentResult(
            context=enrichment_context,
            outputs=outputs,
            enrichment_generation_id=enrichment_generation_id,
        )

    def _transform_segmentation_response(
        self, item: Dict[str, Any], outputs: List[EnrichmentOutput]
    ) -> None:
        """
        Create segmentation outputs from item data if valid.
        """
        try:
            if isinstance(item, list):
                for entity in item:
                    if isinstance(entity, dict):
                        outputs.extend(
                            EnrichmentOutput(type="segmentation2d", value=output)
                            for output in self._create_segmentation_outputs(entity)
                        )
            else:
                print(
                    ELC.MED_IMAGE_INSIGHT_OUTPUT_RESPONSE_WARNING.format(response=item)
                )
        except Exception as e:
            print(EC.ENRICHMENT_UNEXPECTED_ERROR.format(method="_transform_segmentation_response", error=e))
        

    def _create_segmentation_outputs(
        self, entity: Dict[str, Any]
    ) -> List[Segmentation2DOutput]:
        """
        Produce a list of Segmentation2DOutput from base64-encoded masks.
        """
        image_meta_data_list = ModelUtils.retrieve_image_analysis_data(entity)
        return [
            Segmentation2DOutput(
                segmentation_mask=SegmentationMask(rle=image_meta_data.rle),
                height=image_meta_data.height,
                width=image_meta_data.width,
                metadata=image_meta_data.metadata,
            )
            for image_meta_data in image_meta_data_list
        ]
