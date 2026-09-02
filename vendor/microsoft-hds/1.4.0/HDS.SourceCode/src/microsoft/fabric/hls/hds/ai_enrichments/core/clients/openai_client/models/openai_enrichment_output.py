# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------

from typing import List
from pydantic import BaseModel

from microsoft.fabric.hls.hds.ai_enrichments.core.clients.openai_client.models.openai_enrichment_result import OpenAIEnrichmentResult

class OpenAIEnrichmentOutput(BaseModel):
    """
    Collects multiple enrichment results in a single place.
    Each instance includes:
      - enrichmentResult: a list of individual enrichment items
    """
    enrichmentResult: List[OpenAIEnrichmentResult]