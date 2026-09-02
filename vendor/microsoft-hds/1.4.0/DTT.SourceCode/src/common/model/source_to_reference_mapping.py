from pydantic import Field

from common.model.immutable_model import ImmutableModel


class SourceToReferenceMapping(ImmutableModel):
    source_field_name: str = Field(..., description="source field name to be mapped to reference value")
    target_reference_table_name: str = Field(..., description="target reference table name")
    target_reference_field_name: str = Field(..., description="target reference field name")
