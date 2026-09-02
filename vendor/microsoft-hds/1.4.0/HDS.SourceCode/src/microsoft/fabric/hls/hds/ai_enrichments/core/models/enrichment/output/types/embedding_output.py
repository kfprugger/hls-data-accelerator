from typing import Any, List
from pydantic import BaseModel, Field, field_validator

class EmbeddingOutput(BaseModel):
    """  
    EmbeddingOutput represents a model for embedding-based output with associated metadata.  

    Attributes:
        vector (List[float]): A list of vector values.
    """

    vector: List[float] = Field(..., description="List of vector values")

    @field_validator('vector')
    def validate_vector(cls, vector):
        if not vector:
            raise ValueError('vector must not be empty')
        if not all(isinstance(v, float) for v in vector):
            raise ValueError('all elements in vector must be of type float')
        return vector
