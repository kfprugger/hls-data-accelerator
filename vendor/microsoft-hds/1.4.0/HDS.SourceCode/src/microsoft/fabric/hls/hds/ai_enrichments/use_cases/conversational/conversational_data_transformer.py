# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------
from typing import Any, Dict, List, Optional, get_type_hints


from microsoft.fabric.hls.hds.ai_enrichments.core.base_classes.enrichment_transformer_base import (
    EnrichmentTransformerBase,
)
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_constants import (
    AIEnrichmentsConstants as EC,
)
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_context import (
    EnrichmentContext,
)
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_output import (
    EnrichmentOutput,
)
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_response import (
    EnrichmentResponse,
)
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_result import (
    EnrichmentResult,
)
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.terminology import (
    Terminology,
)
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.types.text_output import (
    TextOutput,
)
from microsoft.fabric.hls.hds.ai_enrichments.use_cases.common.constants.enrichment_use_case_constants import (
    EnrichmentUseCaseConstants as EUC,
)

class ConversationalDataTransformer(EnrichmentTransformerBase):
    """
    Transforms conversational enrichment data by mapping raw AI responses
    to structured enrichment objects.
    """

    def __init__(
        self,
        max_workers: int = EC.DEFAULT_AI_ENRICHMENT_EXECUTION_THREADS
    ) -> None:
        """
        Initializes the transformer with Spark session and an optional MSSparkUtils client.

        Args:
            spark (SparkSession): The SparkSession instance.
            logger_name (Optional[str]): The logger name.
            max_workers (int): Number of worker threads.
            mssparkutils_client (Optional[MSSparkUtilsClientBase]): MSSparkUtils client.
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
        Construct the enrichment result object from the given response.

        Args:
            enrichment_generation_id (str): Identifier for the enrichment process.
            enrichment_context (EnrichmentContext): The enrichment context.
            response (EnrichmentResponse): The enrichment response object.

        Returns:
            EnrichmentResult: The constructed enrichment result object.
        """
        outputs: List[EnrichmentOutput] = []
        # Transform the raw response items into a list of output objects
        self._transform_result(response.content, outputs)
        return EnrichmentResult(
            context=enrichment_context,
            outputs=outputs,
            enrichment_generation_id=enrichment_generation_id,
        )

    def _transform_result(
        self, item: Dict[str, Any], outputs: List[EnrichmentOutput]
    ) -> None:
        """
        Iterate over the AI enrichment data and append structured text outputs.

        Args:
            item (Dict[str, Any]): Dictionary containing raw enrichment data.
            outputs (List[EnrichmentOutput]): Collection to store resulting outputs.
        """
        try:
            outputs.extend(
                EnrichmentOutput(
                    type="text",
                    value=self._create_text_output(entity),
                    confidence_score=entity.get("confidence_score"),
                    description="",
                )
                for entity in item.get(EUC.CONVERSATIONAL_DATA_OUTPUT_KEY, [])
                if entity and entity.get("value")
            )
        except Exception as e:
            print(EC.ENRICHMENT_UNEXPECTED_ERROR.format(method="_transform_result", error=e))


    def _create_text_output(self, entity: Dict[str, Any]) -> TextOutput:
        """
        Create a TextOutput object using the provided entity data.

        Args:
            entity (Dict[str, Any]): Dictionary representing an enrichment entity.

        Returns:
            TextOutput: A text-based enrichment output object.
        """
       
           
        field_keys = ["value", "domain", "reasoning"]
        # Build the terminology object, if applicable
        terminology = self._get_terminology(entity)
        # Map known fields onto the TextOutput fields
        return TextOutput(
            **{key: entity.get(key, "") for key in field_keys},
            terminology=terminology,
        )

    def _get_terminology(self, entity: Dict[str, Any]) -> Optional[List[Terminology]]:
        """
        Retrieve the terminology for the given entity based on the use-case configuration.

        Args:
            entity (Dict[str, Any]): Dictionary representing an enrichment entity.

        Returns:
            Optional[List[Terminology]]: Terminology objects if found, otherwise an empty list.
        """
        # Identify the relevant use case configuration from the domain
        use_case_config = EUC.CONVERSATIONAL_DATA_ENRICHMENT_USE_CASES.get(
            entity.get("domain")
        )
        if not use_case_config:
            return []

        terminology_config = use_case_config.get("terminology")
        if not terminology_config:
            return []

        # Map the entity value to a code, falling back to an unspecified mapping
        code_value = terminology_config.get("code_mappings", {}).get(
            entity.get("value"), EUC.UNSPECIFIED_MAPPING
        )
        return [
            Terminology(
                system=terminology_config.get("system"),
                name=terminology_config.get("name"),
                value=code_value,
            )
        ]
