# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------
from pydantic import BaseModel, Field
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.evidence_region import EvidenceRegion



class EvidenceMetadata(BaseModel):
    """
    EvidenceMetadata

    Attributes:
        document_id (str): Unique identifier of the document.
        evidence_region (EvidenceRegion): Modality specific region, which can be a text span or a 2D/3D region/segmentation.
    """
    document_id: str = Field(..., description="Unique identifier of the document")
    evidence_region: EvidenceRegion = Field(..., description="Modality specific region, which can be a text span or a 2D/3D region/segmentation")
