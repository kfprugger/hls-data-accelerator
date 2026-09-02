# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------
from typing import Union
import uuid
from pydantic import BaseModel, Field
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.metadata.enrichment_view_definition import EnrichmentViewDefinition

class EnrichmentView(BaseModel):
    """Model representing an enrichment view."""

    name: str  # Name of the enrichment view
    description: str  # Description of the enrichment view
    definition: Union[EnrichmentViewDefinition, str]   # Definition of the enrichment view
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))  # Unique identifier for the enrichment view

    def to_dict(self):
        """Convert the EnrichmentView instance to a dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "definition": self.definition.to_dict() if isinstance(self.definition, EnrichmentViewDefinition) else self.definition,
            "id": self.id
        }
    
    def __eq__(self, other):
        """Checks for the equality of two EnrichmentView instances."""
        if isinstance(other, EnrichmentView):
            return self.name == other.name and \
                self.definition.parent_views_ids == other.definition.parent_views_ids and \
                self.definition.expression.type == other.definition.expression.type and \
                self.definition.expression.query == other.definition.expression.query
        return False

