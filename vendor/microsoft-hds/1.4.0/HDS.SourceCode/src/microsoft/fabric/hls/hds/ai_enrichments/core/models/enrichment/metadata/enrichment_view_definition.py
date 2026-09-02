# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------
from typing import List, Union
from pydantic import BaseModel
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.metadata.enrichment_view_expression import EnrichmentViewExpression

class EnrichmentViewDefinition(BaseModel):
    """
    Represents the definition of an enrichment view.
    """
    parent_views_ids: List[str]=[]
    expression: Union[EnrichmentViewExpression, str]

    def to_dict(self) -> dict:
        return {
            "parent_views_ids": self.parent_views_ids,
            "expression": self.expression if isinstance(self.expression, str) else self.expression.to_dict(),
        }