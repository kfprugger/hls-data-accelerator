# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------

import json
from typing import List, Optional, Union
from pydantic import BaseModel, Field, model_validator
from microsoft.fabric.hls.hds.ai_enrichments.core.errors.enrichment_value_error import EnrichmentValueError
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.metadata.enrichment_file_reference import EnrichmentFileReference
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_constants import AIEnrichmentsConstants as EC


class EnrichmentInputMapping(BaseModel):
    """
    Represents input mappings for the enrichment process, containing:
      • patient_id: Unique patient identifier.
      • metadata: Custom data, can be dict or string.
      • text_resource_references: List of text file references.
      • image_resource_references: List of image file references.
    """

    patient_id: str
    metadata: Union[dict, str]
    text_resource_references: Optional[List[EnrichmentFileReference]] = Field(
        [],
        description="Optional list of references to text files."
    )
    image_resource_references: Optional[List[EnrichmentFileReference]] = Field(
        [],
        description="Optional list of references to image files."
    )

    @model_validator(mode='after')
    def check_at_least_one_reference(cls, values):
        """
        Ensures at least one resource reference is present.
        Raises EnrichmentValueError if both text and image references are empty.
        """
        text_refs = values.text_resource_references
        image_refs = values.image_resource_references
        if len(text_refs) < 1 and len(image_refs) < 1:
            raise EnrichmentValueError(EC.ENRICHMENT_RESOURCE_REFERENCES_NOT_FOUND)
        return values

    def to_dict(self) -> dict:
        """
        Converts the current object to a dictionary.
        Ensures 'metadata' is serialized if it is a dict.
        """
        return {
            "patient_id": self.patient_id,
            "metadata": json.dumps(self.metadata) if isinstance(self.metadata, dict) else self.metadata,
            "text_resource_references": [ref.to_dict() for ref in self.text_resource_references],
            "image_resource_references": [ref.to_dict() for ref in self.image_resource_references]
        }