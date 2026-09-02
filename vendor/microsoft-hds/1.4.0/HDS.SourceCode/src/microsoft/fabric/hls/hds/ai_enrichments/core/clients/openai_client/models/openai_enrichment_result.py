# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------

from pydantic import BaseModel

class OpenAIEnrichmentResult(BaseModel):
    """
    Represents an individual enrichment result from the AI system.
    Each instance holds:
      - value: the enriched text or phrase or analysis result
      - domain: the classification or category of the enrichment
      - reasoning: the short explanation behind the enrichment
    """
    value: str
    domain: str
    reasoning: str

