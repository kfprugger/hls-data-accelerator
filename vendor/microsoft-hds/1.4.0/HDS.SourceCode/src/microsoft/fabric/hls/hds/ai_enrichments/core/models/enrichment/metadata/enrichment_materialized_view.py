# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------
import uuid
from pydantic import BaseModel, Field

class EnrichmentMaterializedView(BaseModel):
    """Model representing an enrichment materialized view."""

    # Identifier for the view referenced by the materialized view
    view_id: str
    
    # reference to the output path of the materialized view
    reference_materialized_view_path: str
    
    # Name of the materialized view
    name: str
    
    # Unique identifier for the materialized view
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))