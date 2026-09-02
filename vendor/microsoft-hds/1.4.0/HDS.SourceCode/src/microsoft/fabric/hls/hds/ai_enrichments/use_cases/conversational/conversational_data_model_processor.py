# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------
from typing import List

from microsoft.fabric.hls.hds.ai_enrichments.core.base_classes.enrichment_model_processor_base import (
    EnrichmentModelProcessorBase,
)
from microsoft.fabric.hls.hds.ai_enrichments.core.clients.models.enrichment_api_response import (
    EnrichmentAPIResponse,
)
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_constants import (
    AIEnrichmentsConstants as EC,
)
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_context import (
    EnrichmentContext,
)
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_response import (
    EnrichmentResponse,
)
from microsoft.fabric.hls.hds.ai_enrichments.use_cases.common.constants.enrichment_use_case_constants import (
    EnrichmentUseCaseConstants as EUC,
)
from microsoft.fabric.hls.hds.ai_enrichments.use_cases.common.constants.enrichment_use_case_logging_constants import (
    EnrichmentUseCaseLoggingConstants as ELC,
)
from microsoft.fabric.hls.hds.ai_enrichments.use_cases.common.utils.enrichment_model_utils import (
    EnrichmentModelUtils as ModelUtils,
)



class ConversationalDataModelProcessor(EnrichmentModelProcessorBase):
    """
    Orchestrates conversational data processing and OpenAI calls.
    """

    def __init__(
        self,
        data_enrichment_use_case: str = None,
        max_workers: int = EC.DEFAULT_AI_ENRICHMENT_EXECUTION_THREADS,
        execution_batch_size: int = EC.DEFAULT_AI_ENRICHMENT_EXECUTION_BATCH_SIZE
    ) -> None:
        """
        Initialize the conversational data model processor.

        Args:
            spark (SparkSession): The Spark session.
            data_enrichment_use_case (str, optional): The specific data enrichment use case. Defaults to None.
            max_workers (int, optional): The maximum number of worker threads. Defaults to EC.DEFAULT_AI_ENRICHMENT_EXECUTION_THREADS.
            execution_batch_size (int, optional): The batch size for execution. Defaults to EC.DEFAULT_AI_ENRICHMENT_EXECUTION_BATCH_SIZE.
            mssparkutils_client (MSSparkUtilsClientBase, optional): The MSSparkUtils client. Defaults to None.
        """
        super().__init__(
            get_model_client=ModelUtils.get_conversational_client,
            max_workers=max_workers,
            execution_batch_size=execution_batch_size
        )
        self.data_enrichment_use_case = data_enrichment_use_case

    def process(
        self,
        enrichment_id: str,
        model_config: dict,
        enrichment_contexts: List[EnrichmentContext]
    ) -> List[EnrichmentResponse]:
        """
        Process conversational data enrichment by batching inputs.

        Args:
            enrichment_id (str): The enrichment generation ID.
            model_config (dict): The model configuration.
            enrichment_contexts (List[EnrichmentContext]): List of enrichment context objects.
            save_raw_response (bool): Flag to indicate whether to save raw responses.
            output_dir (str): The output directory for saving responses.

        Returns:
            List[EnrichmentResponse]: List of enrichment responses.
        """
        use_cases = (
            [EUC.CONVERSATIONAL_DATA_ENRICHMENT_USE_CASES[self.data_enrichment_use_case]]
            if self.data_enrichment_use_case
            else EUC.CONVERSATIONAL_DATA_ENRICHMENT_USE_CASES.values()
        )
        responses = []
        for use_case in use_cases:
            print(ELC.AI_ENRICHMENT_CONVERSATIONAL_DATA_USECASE_INFO.format(
                use_case_name=use_case["use_case_name"]
            ))
            responses.extend(
                super().process(
                    enrichment_id,
                    {**model_config, **use_case},
                    enrichment_contexts
                )
            )
        return responses

    def post_process_api_responses(
        self,
        enrichment_id: str,
        document_inputs: List[EnrichmentContext],
        results: List[EnrichmentAPIResponse],
    ) -> List[EnrichmentResponse]:
        """
        Convert API responses to EnrichmentResponse objects and save if needed.

        Args:
            enrichment_id (str): The enrichment generation ID.
            document_inputs (List[EnrichmentContext]): List of enrichment context objects.
            results (List[EnrichmentAPIResponse]): List of API responses.
            save_raw_response (bool): Flag to indicate whether to save raw responses.
            raw_response_dir (str): The directory to save raw responses.

        Returns:
            List[EnrichmentResponse]: List of enrichment responses.
        """
        final_responses = []
        for i, result in enumerate(results):
            response = EnrichmentResponse(
                id=document_inputs[i].enrichment_input.text_file_references[0].id,
                content=result.data,
            )
            final_responses.append(response)
        return final_responses
