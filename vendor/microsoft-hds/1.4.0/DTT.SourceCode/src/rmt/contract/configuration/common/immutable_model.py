from pydantic import BaseModel, ConfigDict


class ImmutableModel(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
