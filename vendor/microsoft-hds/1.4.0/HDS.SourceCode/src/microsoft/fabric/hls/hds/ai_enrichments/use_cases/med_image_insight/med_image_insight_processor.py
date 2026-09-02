# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------

from typing import List
from microsoft.fabric.hls.hds.ai_enrichments.core.base_classes.enrichment_model_processor_base import EnrichmentModelProcessorBase
from microsoft.fabric.hls.hds.ai_enrichments.core.clients.models.enrichment_api_response import EnrichmentAPIResponse
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_constants import AIEnrichmentsConstants as EC
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_context import EnrichmentContext
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_response import EnrichmentResponse
from microsoft.fabric.hls.hds.ai_enrichments.use_cases.common.utils.enrichment_model_utils import EnrichmentModelUtils as ModelUtils


class MedImageInsightProcessor(EnrichmentModelProcessorBase):
    """
    This processor class handles medical image enrichment.
    It leverages a model client to execute inference on batches
    of medical image content.
    """

    def __init__(
        self,
        max_workers: int = EC.DEFAULT_AI_ENRICHMENT_EXECUTION_THREADS,
        execution_batch_size: int = EC.DEFAULT_AI_ENRICHMENT_EXECUTION_BATCH_SIZE
    ) -> None:
        """
        Initializes the MedImageInsightProcessor.

        Args:
            spark (SparkSession): Spark session instance.
            max_workers (int, optional): Number of threads used for parallel processing. Defaults to EC.DEFAULT_AI_ENRICHMENT_EXECUTION_THREADS.
            execution_batch_size (int, optional): Batch size for each inference round. Defaults to EC.DEFAULT_AI_ENRICHMENT_EXECUTION_BATCH_SIZE.
            mssparkutils_client (MSSparkUtilsClientBase, optional): Optional client for Spark utilities. Defaults to None.
        """
        super().__init__(
            get_model_client=ModelUtils.get_med_image_client,
            max_workers=max_workers,
            execution_batch_size=execution_batch_size,
        )

    
    
    def post_process_api_responses(
        self,
        enrichment_id: str,
        document_inputs: List[EnrichmentContext],
        results: EnrichmentAPIResponse
    ) -> List[EnrichmentResponse]:
        """
        Finalizes the responses from the medical image model and converts them
        into a structured format.

        Args:
            enrichment_id (str): Unique identifier for the enrichment run.
            document_inputs (List[EnrichmentContext]): Original enrichment contexts.
            results (EnrichmentAPIResponse): Raw API response from the model.
            save_raw_response (bool): Flag indicating if raw output must be saved.
            raw_response_dir (str): Destination path for raw model output.

        Returns:
            List[EnrichmentResponse]: A list of formatted EnrichmentResponse objects.
        """
        return ModelUtils.format_analysis_results(
            enrichment_id,
            document_inputs,
            results
        )
