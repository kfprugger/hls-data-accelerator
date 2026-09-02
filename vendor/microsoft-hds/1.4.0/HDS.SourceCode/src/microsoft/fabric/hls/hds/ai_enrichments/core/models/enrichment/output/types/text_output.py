from typing import List, Optional  
from pydantic import BaseModel, Field, field_validator
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.evidence import Evidence
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.terminology import Terminology

  
class TextOutput(BaseModel):  
    """  
    TextOutput represents a model for text-based output with associated metadata.  
  
    Attributes:  
        value (str): The main text value.  
        domain (Optional[str]): The domain or context of the value.  
        reasoning (Optional[str]): The reasoning or explanation behind the value.  
        evidence (List[Evidence]): A list of evidence supporting the value.  
        terminology (List[Terminology]): A list of terminology references related to the value.  
    """  
  
    value: str = Field(..., description="Value")  
    domain: Optional[str] = Field(None, description="Domain of the value.")  
    reasoning: Optional[str] = Field(None, description="Reasoning")  
    evidence: List[Evidence] = Field(default_factory=list, description="List of 'evidence' values")  
    terminology: List[Terminology] = Field(default_factory=list, description="Terminology reference")  
  
    @field_validator('value')  
    def validate_value(cls, value):  
        if not value.strip():  
            raise ValueError('value must not be empty or whitespace')  
        return value  
  
