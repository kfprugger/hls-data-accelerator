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


class MedImageParseProcessor(EnrichmentModelProcessorBase):
    """
    Responsible for handling the segmentation of healthcare images using the MedImageParse model.
    Inherits from EnrichmentModelProcessorBase to ensure consistent enrichment workflow.
    """

    def __init__(
        self,
        max_workers: int = EC.DEFAULT_AI_ENRICHMENT_EXECUTION_THREADS,
        execution_batch_size: int = EC.DEFAULT_AI_ENRICHMENT_EXECUTION_BATCH_SIZE
    ) -> None:
        """
        Initializes the MedImageParseProcessor with required Spark session, model configuration, and threading variables.

        Args:
            spark (SparkSession): The active Spark session.
            max_workers (int): Number of worker threads to use for processing.
            execution_batch_size (int): Number of items to process in a single batch.
            mssparkutils_client (MSSparkUtilsClientBase, optional): Azure Spark utility client for I/O operations.
        """
        super().__init__(
            get_model_client=ModelUtils.get_med_image_client,
            max_workers=max_workers,
            execution_batch_size=execution_batch_size
        )
    
    def post_process_api_responses(
        self,
        enrichment_generation_id: str,
        document_inputs: List[EnrichmentContext],
        results: List[EnrichmentAPIResponse]
    ) -> List[EnrichmentResponse]:
        """
        Processes the model responses to produce refined MedImageParse enrichment results.

        Args:
            enrichment_generation_id (str): Identifier for tracking the current run of enrichments.
            document_inputs (List[EnrichmentContext]): All document inputs for the batch.
            results (EnrichmentAPIResponse): Raw responses received from the model.
            should_save_raw_response (bool): Whether to store the original responses.
            raw_response_output_path (str): Path for saving any raw response data.

        Returns:
            List[EnrichmentResponse]: Final structured results ready for downstream use.
        """        
        return ModelUtils.format_analysis_results(
            enrichment_generation_id,
            document_inputs,
            results
        )