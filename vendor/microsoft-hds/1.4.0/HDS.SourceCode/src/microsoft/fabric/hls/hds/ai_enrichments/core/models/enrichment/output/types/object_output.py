from typing import Any, List, Optional
from pydantic import BaseModel, Field, field_validator
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.evidence import Evidence



class ObjectOutput(BaseModel):
    """
    A class used to represent the output of an object.

    Attributes:
        type (str): The type of the object output.
        value (Any): The value of the object output.
        reasoning (Optional[str]): The reasoning behind the object output.
        evidence (List[Evidence]): A list of evidence supporting the object output.
    """

    type: str
    value: Any
    reasoning: Optional[str] = None
    evidence: List[Evidence] = Field(default_factory=list)

    @field_validator('type')
    def type_must_not_be_empty_or_none(cls, v):
        if v is None or v.strip() == '':
            raise ValueError('type must not be empty or None')
        return v

    @field_validator('value')
    def value_must_not_be_none(cls, v):
        if v is None:
            raise ValueError('value must not be None')
        return v
