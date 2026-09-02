# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
from pydantic import BaseModel, Field, model_validator
from typing import Dict
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_constants import AIEnrichmentsConstants as EC
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_logging_constants import AIEnrichmentsLoggingConstants as ELC

class OpenAIClientSettings(BaseModel):
    azure_endpoint: str
    api_key: str
    api_version: str
    open_ai_config_options: Dict[str, str] = Field(default_factory=dict)
    model_name: str = Field(default=EC.MODEL_NAME)

    @model_validator(mode='after') 
    def check_not_empty(cls, values):
        if not values.azure_endpoint or not values.api_key:
            raise ValueError(ELC.OPENAI_ENRICHMENT_MODEL_CONFIG_ERROR)
        return values