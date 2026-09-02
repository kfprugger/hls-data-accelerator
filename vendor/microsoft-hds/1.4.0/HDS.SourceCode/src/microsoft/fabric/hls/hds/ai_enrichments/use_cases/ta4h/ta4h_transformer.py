# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------

from typing import Any, Dict, List, OrderedDict
from datetime import datetime, timezone
from microsoft.fabric.hls.hds.ai_enrichments.core.base_classes.enrichment_transformer_base import EnrichmentTransformerBase
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_constants import AIEnrichmentsConstants as EC
from microsoft.fabric.hls.hds.ai_enrichments.core.errors.enrichment_value_error import EnrichmentValueError
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_context import EnrichmentContext
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_output import EnrichmentOutput
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_response import EnrichmentResponse
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_result import EnrichmentResult
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.evidence import Evidence
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.evidence_metadata import EvidenceMetadata
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.evidence_region import EvidenceRegion
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.fhir_resource_transform_config import FHIRResourceTransformConfig
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.terminology import Terminology
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.text_span import TextSpan
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.types.object_output import ObjectOutput
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.types.text_output import TextOutput
from microsoft.fabric.hls.hds.ai_enrichments.core.utils.ai_enrichments_utils import AIEnrichmentsUtils
from microsoft.fabric.hls.hds.ai_enrichments.core.utils.ai_enrichments_fhir_utils import AIEnrichmentsFHIRUtils
from microsoft.fabric.hls.hds.ai_enrichments.use_cases.common.constants.enrichment_use_case_constants import (
    EnrichmentUseCaseConstants as EUC,
)


class TA4HTransformer(EnrichmentTransformerBase):
    """
    Transforms raw TA4H response data into enriched results, utilizing relevant metadata
    and context to generate outputs such as text or object enrichments.
    """

    def __init__(
        self,
        max_workers: int = EC.DEFAULT_AI_ENRICHMENT_EXECUTION_THREADS,
        fhir_resources_config: Dict[str, FHIRResourceTransformConfig] = EUC.FHIR_RESOURCES_CONFIG,
    ) -> None:
        """
        Initialize the TA4HTransformer.

        Args:
            spark: The SparkSession instance.
            logger_name: Name used for the logger.
            max_workers: Maximum number of worker threads.
            mssparkutils_client: An optional mssparkutils client instance.
        """
        super().__init__(
            max_workers=max_workers
        )
        self.fhir_resources_config = fhir_resources_config
        for resource_type, config in self.fhir_resources_config.items():
            if not isinstance(config, FHIRResourceTransformConfig):
                raise EnrichmentValueError(f"Invalid FHIR resource extraction configuration for '{resource_type}'.")
            config.value_transformers=dict(
                  subject=AIEnrichmentsFHIRUtils.update_patient_reference,
                  patient=AIEnrichmentsFHIRUtils.update_patient_reference,
            )

    def build_enrichment_result(
        self,
        enrichment_generation_id: str,
        enrichment_context: EnrichmentContext,
        response: EnrichmentResponse,
    ) -> EnrichmentResult:
        """
        Construct the enrichment result object with TA4H transformation outputs.

        Args:
            enrichment_generation_id: Unique ID representing the enrichment generation.
            enrichment_context: The context data for enrichments.
            response: The raw enrichment response from TA4H.

        Returns:
            EnrichmentResult: Contains context, outputs, and generation info.
        """
      
        enrichment_context.enrichment_input.text_file_references[0].content = (
            AIEnrichmentsUtils.get_base64_encoded_string(
                enrichment_context.enrichment_input.text_file_references[0].content
            )
        )
        outputs: List[EnrichmentOutput] = []
        self._transform_entities_and_relations(enrichment_context,response.content, outputs)
        
        return EnrichmentResult(
            context=enrichment_context,
            outputs=outputs,
            enrichment_generation_id=enrichment_generation_id,
        )

    def _transform_entities_and_relations(
        self,
        enrichment_context: EnrichmentContext,
        item_data: Dict[str, Any],
        outputs: List[EnrichmentOutput]
    ) -> None:
        """
        Extract and transform entity and relation information to produce text or object outputs.

        Args:
            item_data: Dictionary with "entities" and "relations" data.
            outputs: The list to which the transformed outputs will be appended.
        """
        try:
            # Transform entities
            for entity in item_data.get("entities", []):
                text_output = self._create_text_output(entity)
                output_schema = EnrichmentOutput(
                    type="text",
                    value=text_output,
                    confidence_score=entity.get("confidence_score", 0.0),
                    description="",
                )
                outputs.append(output_schema)

            # Transform relations
            for relation in item_data.get("relations", []):
                if not relation:
                    continue
                object_output = self._create_object_output(
                    enrichment_context,
                    relation.get("roles", []),
                    relation.get("relation_type", "")
                )
                outputs.append(EnrichmentOutput(type="object", value=object_output))

            # Transform FHIR bundle
            fhir_bundle_data = item_data.get("fhir_bundle",None)
            if fhir_bundle_data:
                fhir_bundle = fhir_bundle_data
                object_output = self._create_object_output(enrichment_context,fhir_bundle)
                outputs.append(EnrichmentOutput(type="object", value=object_output))
                
        except Exception as e:
            print(f"Error transforming entities and relations: {e}")

    def _create_text_output(self, entity: Dict[str, Any]) -> TextOutput:
        """
        Create a TextOutput object from a given entity dictionary.

        Args:
            entity: Dictionary containing entity details (text, offset, length, etc.).

        Returns:
            TextOutput: Describes the text entity with associated metadata.
        """
        data_sources = entity.get("data_sources", [])
        terminology = [
            Terminology(name=src["name"], value=src["entity_id"], system="")
            for src in data_sources
        ]
        evidence = Evidence(
            type="text_span",
            evidence=EvidenceMetadata(
                document_id="",
                evidence_region=EvidenceRegion(
                    text_span=TextSpan(
                        start_position=entity.get("offset", 0),
                        end_position=entity.get("offset", 0) + entity.get("length", 0),
                    )
                ),
            ),
        )
        return TextOutput(
            value=entity.get("text", ""),
            domain=entity.get("category", ""),
            reasoning="",
            evidence=[evidence],
            terminology=terminology,
        )

    def _create_object_output(self, enrichment_context:EnrichmentContext,data: Dict[str, Any], output_type: str = "FHIR") -> ObjectOutput:
        """
        Create an ObjectOutput object from a given dictionary.

        Args:
            data: Dictionary containing details (relation_type, roles, FHIR bundle, etc.).
            output_type: The type of the object output (e.g., "object", "FHIR").

        Returns:
            ObjectOutput: Describes the object with associated metadata.
        """
        if output_type == "FHIR":
            fhir_resources = TA4HTransformer._extract_fhir_resources(enrichment_context,data, self.fhir_resources_config)
            return ObjectOutput(
                type=output_type ,
                value=fhir_resources,
                reasoning="",
                evidence=[],
                terminology=[],
            )
        return ObjectOutput(
            type=output_type ,
            value=data,
            reasoning="",
            evidence=[],
            terminology=[],
        )
        
    @staticmethod   
    def _extract_fhir_resources(
        enrichment_context: EnrichmentContext,
        enrichment_result: dict,
        extraction_configs: Dict[str, FHIRResourceTransformConfig]
    ) -> List[Dict]:
            """
            Extracts FHIR resources from an NDJSON enrichment file based on the provided extraction configurations.

            Args:
                lines (str): The NDJSON content as a string.
                extraction_configs (Dict[str, FHIRResourceExtractionConfig]): Configuration for extracting FHIR resources.

            Returns:
                Dict[str, List[Dict]]: A dictionary of extracted FHIR resources grouped by resource type.
            """
            try:
                fhir_resources = []
                current_resources = TA4HTransformer._extract_resource_properties(
                            enrichment_result,
                           enrichment_context, extraction_configs
                )                  
                if current_resources:
                            fhir_resources.extend(current_resources)
                return fhir_resources

            except Exception as e:
                print(f"Error extracting FHIR resources: {e}")
                return {}
    
    @staticmethod
    def _extract_resource_properties(
    fhirBundle: Dict,
    enrichment_context: EnrichmentContext,
    extraction_configs: Dict, 
) -> List[Dict]:
        """
            Given a TA4H bundle, extract the requested resources according
            to the requested config.
        """
        try:
            resources_in_bundle = fhirBundle.get("entry")
            if not resources_in_bundle:
                return []
            extracted_fhir_resources = []
            for curr_resource in resources_in_bundle:
                curr_resource = curr_resource.get("resource")
                if not curr_resource:
                    continue
                resource_type = curr_resource.get("resourceType")
                if not resource_type or resource_type not in extraction_configs:
                    continue 
                res_extract_config = extraction_configs[resource_type]
                properties = res_extract_config.properties
                value_transformers = res_extract_config.value_transformers
                new_resource = OrderedDict()
                for p in properties:
                    if p not in curr_resource:
                        continue
                    k = p
                    if p in value_transformers:
                        v = value_transformers[p](curr_resource, p, enrichment_context)
                    else:
                        if p not in curr_resource:
                            raise Exception(f"{p} not found in the current resource")
                        v = curr_resource[p]
                    new_resource[k] = v                    
                if new_resource:
                    now = datetime.now(timezone.utc)
                    last_updated = now.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
                
                    AIEnrichmentsFHIRUtils.add_enrichment_identifier(new_resource, enrichment_context)

                    if "meta" in new_resource:
                        new_resource["meta"]["aienrichmentcontextid"] = enrichment_context.enrichment_context_id
                        new_resource["meta"]["lastUpdated"] = last_updated
                    else:
                        new_resource["meta"] = {
                            "aienrichmentcontextid": enrichment_context.enrichment_context_id,
                            "lastUpdated": last_updated
                        }
                    extracted_fhir_resources.append(new_resource)
            return extracted_fhir_resources
        except Exception as e:

            print(f"Error extracting resource properties: {e}")
            return []



