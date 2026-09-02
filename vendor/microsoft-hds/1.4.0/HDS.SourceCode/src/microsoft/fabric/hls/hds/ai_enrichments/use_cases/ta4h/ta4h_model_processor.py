# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------
from typing import List
from microsoft.fabric.hls.hds.ai_enrichments.core.base_classes.enrichment_model_processor_base import EnrichmentModelProcessorBase
from microsoft.fabric.hls.hds.ai_enrichments.core.clients.models.enrichment_api_response import EnrichmentAPIResponse
from microsoft.fabric.hls.hds.ai_enrichments.core.clients.ta4h_client_orchestrator import TA4hClientOrchestrator
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_constants import AIEnrichmentsConstants as EC
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_context import EnrichmentContext
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_response import EnrichmentResponse



class TA4HModelProcessor(EnrichmentModelProcessorBase):
    """
    Processes healthcare entities using Azure Text Analytics for Health.
    """

    def __init__(
        self,
        max_workers: int = EC.DEFAULT_AI_ENRICHMENT_EXECUTION_THREADS,
        execution_batch_size: int = EC.DEFAULT_AI_ENRICHMENT_EXECUTION_BATCH_SIZE,
    ) -> None:
        """
        Initializes the TA4HModelProcessor with specified configurations.

        Args:
            spark (SparkSession): Active Spark session.
            max_workers (int): Maximum worker threads.
            execution_batch_size (int): Batch size for enrichment.
            mssparkutils_client (MSSparkUtilsClientBase): Spark utilities client.
        """
        super().__init__(
            get_model_client=TA4HModelProcessor.get_ta4h_client,
            max_workers=max_workers,
            execution_batch_size=execution_batch_size,
        )

    @staticmethod
    def get_ta4h_client(
        model_config: dict
    ) -> TA4hClientOrchestrator:
        """
        Creates and returns a TA4H client orchestrator.

        Args:
            model_config (dict): Model configuration.

        Returns:
            TA4hClientOrchestrator: Client for TA4H processing.
        """
        return TA4hClientOrchestrator(
            api_endpoint=model_config.get("api_endpoint"),
            api_key=model_config.get("api_key"),
            fhir_version=model_config.get("fhir_version", None),
            model_version=model_config.get("version", None),
        )
        
    def post_process_api_responses(
        self,
        enrichment_generation_id: str,
        document_inputs: List[EnrichmentContext],
        results: List[EnrichmentAPIResponse],
    ) -> List[EnrichmentResponse]:
        """
        Prepares JSON output from API analysis results.

        Args:
            enrichment_generation_id (str): Enrichment generation identifier.
            document_inputs (List[EnrichmentContext]): Document inputs list.
            results (EnrichmentAPIResponse): API response data.
            should_save_raw_response (bool): Toggle for raw response storage.
            raw_response_output_path (str): File path for raw response.

        Returns:
            List[EnrichmentResponse]: Processed enrichment responses.
        """

        processed_responses = []
        for api_result in results:
                if api_result.is_completed and api_result.data:
                    doc_data = api_result.data
                    formatted_result = {
                        "id": doc_data.id,
                        "entities": [
                            {
                                "text": entity.text,
                                "category": entity.category,
                                "subcategory": entity.subcategory,
                                "confidence_score": entity.confidence_score,
                                "offset": entity.offset,
                                "length": entity.length,
                                "data_sources": [
                                    {"name": source.name, "entity_id": source.entity_id}
                                    for source in (entity.data_sources or [])
                                ],
                            }
                            for entity in (doc_data.entities or [])
                        ],
                        "relations": [
                            {
                                "relation_type": relation.relation_type,
                                "roles": [
                                    {"name": role.name, "entity": role.entity.text}
                                    for role in (relation.roles or [])
                                ],
                            }
                            for relation in (doc_data.entity_relations or [])
                        ],
                        "fhir_bundle": doc_data.fhir_bundle
                    }
                    enrichment_response = EnrichmentResponse(
                        id=document_inputs[int(doc_data.id)]
                        .enrichment_input.text_file_references[0]
                        .id,
                        content=formatted_result,
                    )
                    processed_responses.append(enrichment_response)
        return processed_responses