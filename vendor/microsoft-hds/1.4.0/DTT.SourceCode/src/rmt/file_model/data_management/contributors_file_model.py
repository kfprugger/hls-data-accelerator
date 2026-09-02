import json
from typing import List

from pydantic import BaseModel, Field


class NoExtrasBaseModel(BaseModel):
    class Config:
        extra = "forbid"


class ContributorRange(BaseModel):
    min: int = Field(..., description="The start of the range")
    max: int = Field(..., description="The end of the range")


class ContributorFileModel(BaseModel):
    contributor: str = Field(..., description="The name of the contributor")
    idRange: ContributorRange = Field(..., description="The range of the contributor")


class ContributorsFileModel(BaseModel):
    contributors: List[ContributorFileModel] = Field(..., description="A collection of contributors")

    @classmethod
    def from_str(cls, reference_mapping_str: str) -> "ContributorFileModel":
        return cls(**json.loads(reference_mapping_str))
