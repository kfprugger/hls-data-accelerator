# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------
from typing import Optional, Union  
from pydantic import BaseModel, Field
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_input import EnrichmentInput
class EnrichmentContext(BaseModel):  
    """  
    Context class used for representing the context of an enrichment process.  

    Attributes:  
        enrichment_context_id (Optional[str]): Enrichment Context Id, default is None.  
        model_configuration (Union[dict, str]): Configuration of the model, default is None.  
        enrichment_input (Optional[EnrichmentInput]): Input data for enrichment, default is None.  
    """  
    enrichment_context_id: Optional[str] = Field(None, description="Enrichment Context Id")  
    model_configuration:Optional[Union[dict, str]] = Field(None, description="Configuration of the model")  
    enrichment_input: Optional[EnrichmentInput] = Field(None, description="Input data for enrichment")  
    
    def to_dict(self) -> dict:
        """
        Convert the EnrichmentContext instance to a dictionary.

        Returns:
            dict: A dictionary representation of the EnrichmentContext instance.
        """
        return {
            "enrichment_context_id": self.enrichment_context_id,
            "model_configuration": self.model_configuration,
            "enrichment_input": self.enrichment_input.to_dict() if self.enrichment_input else None
        }