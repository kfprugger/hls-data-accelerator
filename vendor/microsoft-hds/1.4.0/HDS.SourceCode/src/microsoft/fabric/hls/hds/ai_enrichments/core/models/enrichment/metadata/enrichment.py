# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------

from datetime import datetime
from typing import Optional, Union
import uuid
from pydantic import BaseModel, Field

from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.metadata.enrichment_definition import EnrichmentDefinition

class Enrichment(BaseModel):
    """Model representing an enrichment."""
        
    # Name of the enrichment
    name: str
    
    # Description of the enrichment
    description: str
        
    # Definition or details of the enrichment
    definition: Union[EnrichmentDefinition,str]
    
    # Unique identifier for the enrichment (optional)
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))