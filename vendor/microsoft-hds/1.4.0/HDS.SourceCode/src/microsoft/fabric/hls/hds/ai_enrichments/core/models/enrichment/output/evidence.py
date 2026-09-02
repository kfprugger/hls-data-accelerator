# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------
from pydantic import BaseModel, Field, field_validator  
from typing import Literal
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.evidence_metadata import EvidenceMetadata 


class Evidence(BaseModel):  
    """  
    A class to represent an Evidence object.  

    Attributes:  
        type (str): The type of the evidence object.  
        evidence (EvidenceMetadata): The evidence metadata object.  
    """  

    type: Literal["structured", "text_span", "bounding_box", "segmentation_2d", "segmentation_3d"] = Field(  
        ..., description="The type of the evidence object"  
    )  
    evidence: EvidenceMetadata  

    @field_validator('evidence')  
    def validate_evidence(cls, evidence_value):  
        if not isinstance(evidence_value, EvidenceMetadata):  
            raise ValueError('evidence must be an instance of EvidenceMetadata')  
        return evidence_value  

