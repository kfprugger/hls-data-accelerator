# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
from dataclasses import dataclass
from microsoft.fabric.hls.hds.ai_enrichments.core.clients.openai_client.models.openai_model_response_status import OpenAIModelResponseStatus

@dataclass
class OpenAIModelResponse:
    """
    Data class to represent the response from an OpenAI model.
    
    Attributes:
        status (OpenAIModelResponseStatus): The status of the response.
        response (str): The actual response content from the OpenAI model.
    """
    status: OpenAIModelResponseStatus
    response: str  # The actual response content from the OpenAI model, represented as a string
