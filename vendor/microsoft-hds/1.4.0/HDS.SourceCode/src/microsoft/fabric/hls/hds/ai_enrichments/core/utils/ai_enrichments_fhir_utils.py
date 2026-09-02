# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------
from typing import Dict
from microsoft.fabric.hls.hds.ai_enrichments.core.errors.enrichment_value_error import EnrichmentValueError
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_context import EnrichmentContext


class AIEnrichmentsFHIRUtils:
    """
    Utility class for common FHIR-related operations within AI Enrichments.
    """
        
    @staticmethod
    def add_enrichment_identifier(new_resource: Dict, enrichment_context: EnrichmentContext) -> None:
        
        source_system = enrichment_context.enrichment_input.metadata["source_system"] if "source_system" in enrichment_context.enrichment_input.metadata else "Fabric-HDS"
        identifier_value = {
			"use": "temp",
			"type": {
				"coding": [
					{   
						"system": "http://terminology.hl7.org/CodeSystem/v2-0203",
						"code": "AIEnrichmentContextId",
						"display": "AI enrichment context id"            
					}            
				],            
				"text": "AI enrichment context id"        
			},
			"system": source_system,
			"value": enrichment_context.enrichment_context_id,
			"assigner": {}
        }
        
        if "identifier" in new_resource:
            if not isinstance(new_resource["identifier"], list):
                new_resource["identifier"] = [new_resource["identifier"], identifier_value]
            else:
                new_resource["identifier"].append(identifier_value)
        else:
            new_resource["identifier"] = [identifier_value]


    @staticmethod
    def update_patient_reference(fhir_resource: Dict, property_name: str, enrichment_context: EnrichmentContext) -> Dict:
        """
        Updates the patient ID in the FHIR resource's subject or patient field using the patient ID from the enrichment context.

        Args:
            fhir_resource (Dict): The FHIR resource containing the subject or patient field.
            property_name (str): The property to update (typically "subject" or "patient").
            enrichment_context (EnrichmentContext): The enrichment context containing the patient ID.

        Returns:
            Dict: The updated patient reference field dictionary (e.g., {"reference": "Patient/new_id", ...}).

        Raises:
            EnrichmentValueError: If the property is invalid, the reference format is wrong, or the patient ID is missing.
        """
        # Validate the subject field and its reference
        patient_reference_field = fhir_resource.get(property_name)
        if not patient_reference_field or "reference" not in patient_reference_field or not isinstance(patient_reference_field.get("reference"), str) or not patient_reference_field["reference"].startswith("Patient/"):
            raise EnrichmentValueError(f"Invalid or missing 'reference' in the '{property_name}' field.")

        # Retrieve the patient ID from the enrichment context
        if not enrichment_context or not enrichment_context.enrichment_input:
             raise EnrichmentValueError("Enrichment context or enrichment input is missing.")
        patient_id = enrichment_context.enrichment_input.patient_id
        if not patient_id:
            raise EnrichmentValueError("Patient ID is missing in the enrichment context.")

        if "identifier" in patient_reference_field:
            patient_reference_field.pop("identifier", None)

        # Update the reference
        updated_reference = f"Patient/{patient_id}"
        patient_reference_field.update({
            "reference": updated_reference
        })

        return patient_reference_field
    
    