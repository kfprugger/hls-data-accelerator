# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------
from typing import Optional, Union
from pydantic import BaseModel, Field, field_validator
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.text_span import TextSpan


class ResourceReference(BaseModel):
    """
    A model representing a reference to a  resource and its content.

    Attributes:
        id (str): Unique identifier for the text resource.
        content (Optional[str]): Optional content of the text resource.
        section (Optional[TextSpan]): Optional section of the text resource, represented by a TextSpan object.
    """

    id: str = Field(..., description="Unique identifier for the text resource")
    content: Optional[Union[str]] = Field(None, description="Full serialized resource content or text content of the document slice according to the text span")
    section: Optional[TextSpan] = Field(None, description="Optional section of the text resource, represented by a TextSpan object")
    file_content: Optional[Union[str,bytes]] = Field(None, description="Optional content of the file")
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "file_content": self.file_content,
            "section": self.section.to_dict() if self.section else None
        }

    @field_validator('id')
    def validate_id(cls, id_value):
        if not id_value.strip():
            raise ValueError('id must not be empty or whitespace')
        return id_value
