# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------
import json
from typing import Union
from pydantic import BaseModel
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.metadata.enrichment_input_mapping import EnrichmentInputMapping

class EnrichmentDefinition(BaseModel):
    """
    EnrichmentDefinition is a data model class that represents the definition of an enrichment process.
    """
    model: Union[dict, str]
    view_id: str
    input_mapping: Union[EnrichmentInputMapping, str]

    def to_dict(self) -> dict:
        return {
            "model": json.dumps(self.model) if isinstance(self.model, dict) else self.model,
            "view_id": self.view_id,
            "input_mapping": self.input_mapping.to_dict() if isinstance(self.input_mapping, EnrichmentInputMapping) else self.input_mapping
        }