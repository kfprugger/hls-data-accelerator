# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------

from pydantic import BaseModel, model_validator
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_constants import AIEnrichmentsConstants as EC

class EnrichmentFileReference(BaseModel):
    """
    A class used to represent a reference to an record which will be enriched by the enrichment process.
    """
    id: str
    content: str

    @model_validator(mode='after') 
    def check_not_empty(cls, values):
        if not values.id or not values.content:
            raise ValueError(EC.ENRICHMENT_ID_AND_CONTENT_NOT_EMPTY)
        return values

    def to_dict(self) -> dict:
        return self.model_dump()