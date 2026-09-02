# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.resource_reference import ResourceReference

class EnrichmentInput(BaseModel):
    """
    EnrichmentInput model for the enrichment process.

    Attributes:
        patient_id (str): Unique identifier for the patient.
        metadata (Dict[str, Any]): Metadata associated with the enrichment process, stored as a dictionary.
        text_file_references (List[ResourceReference]): List of references to text files, using the ResourceReference model.
        image_file_references (List[ResourceReference]): Optional list of references to image files.
    """
    patient_id: str = Field(..., description="Unique identifier for the patient")
    metadata: Dict[str, Any] = Field(..., description="Metadata associated with the enrichment process, stored as a dictionary")
    text_file_references: Optional[List[ResourceReference]] = Field(None, description="Optional List of references to text files, using the ResourceReference model")
    image_file_references: Optional[List[ResourceReference]] = Field(None, description="Optional list of references to image files using the ResourceReference model")

    def to_dict(self) -> dict:
        """
        Convert the EnrichmentInput instance to a dictionary.

        Returns:
            dict: A dictionary representation of the EnrichmentInput instance.
        """
        return {
            "patient_id": self.patient_id,
            "metadata": self.metadata,
            "text_file_references": [ref.to_dict() for ref in self.text_file_references] if self.text_file_references else [],
            "image_file_references": [ref.to_dict() for ref in self.image_file_references] if self.image_file_references else []
        }