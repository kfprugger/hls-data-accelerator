# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
from dataclasses import dataclass, field
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_constants import AIEnrichmentsConstants as EC

@dataclass
class OpenAIModelSettings:
    """
    Class representing the settings for OpenAI Model API Settings.
    """
    temperature: float = EC.DEFAULT_TEMPERATURE  # Temperature setting for the model
    top_p: float = EC.DEFAULT_TOP_P  # Top-p (nucleus sampling) setting for the model
    frequency_penalty: float = EC.DEFAULT_FREQUENCY_PENALTY  # Frequency penalty setting for the model
    presence_penalty: float = EC.DEFAULT_PRESENCE_PENALTY  # Presence penalty setting for the model
    stop: str = EC.DEFAULT_STOP  # Stop sequence setting for the model
    stream: bool = EC.DEFAULT_STREAM  # Stream setting for the model
    response_format: dict = field(default_factory=lambda: {})  # Response format setting for the model, defaulting to an empty dictionary
