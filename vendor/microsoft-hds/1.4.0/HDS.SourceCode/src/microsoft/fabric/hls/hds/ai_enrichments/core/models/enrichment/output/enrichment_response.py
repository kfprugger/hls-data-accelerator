# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------
from typing import Any
from pydantic import BaseModel, Field

class EnrichmentResponse(BaseModel):
    """
    Model representing the response of an enrichment raw response.
    """
    id: str = Field(..., description="The unique identifier for the record which is being enriched")
    content: Any = Field(..., description="The raw response from the enrichment model")