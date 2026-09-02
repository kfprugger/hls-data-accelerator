# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
from dataclasses import dataclass,field
from typing import Optional
from microsoft.fabric.hls.hds.ai_enrichments.core.clients.openai_client.models.openai_response_status import OpenAIResponseStatus

@dataclass
class OpenAIModelResponseStatus:
    """
    Status class represents the outcome of an operation with details about the result and any errors.

    Attributes:
        result (OpenAIResponseStatus): The result of the operation, default is OpenAIResponseStatus.SUCCESS.
        error_details (Optional[str]): Detailed information about any error that occurred, default is an empty string.
        error_type (Optional[str]): The type of error that occurred, default is an empty string.
    """
    result: OpenAIResponseStatus = field(default_factory=lambda: OpenAIResponseStatus.SUCCESS)
    error_details: Optional[str] = field(default="")
    error_type: Optional[str] = field(default=None)
    retry_count: int = field(default=0)
    retriable: Optional[bool] = field(default=None)