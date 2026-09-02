# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------

import uuid
from pydantic import BaseModel, Field

class GeneratedEnrichment(BaseModel):
    """Model representing generated enrichment."""
    materialize_view_id: str = Field(..., description="Identifier for the materialized view")
    input_name: str = Field(..., description="Name of the input table")
    name: str = Field(None, description="Name or description of the enrichment")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique identifier for the enrichment, generated if not provided")
