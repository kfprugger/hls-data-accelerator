from pydantic import Field

from common.model.source_to_reference_mapping import SourceToReferenceMapping


class SourceToReferenceMappingExtended(SourceToReferenceMapping):
    mapped_column_name: str = Field(..., description="A name of the column in the output")
