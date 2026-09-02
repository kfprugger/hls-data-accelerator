# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------
from typing import Union, Optional, Literal  
from pydantic import BaseModel, Field
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.types.object_output import ObjectOutput
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.types.segmentation_2d_output import Segmentation2DOutput
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.types.text_output import TextOutput
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.types.embedding_output import EmbeddingOutput


class EnrichmentOutput(BaseModel):  
    """  
    EnrichmentOutput is a data model representing the output of an enrichment process.  

    Attributes:  
        type (str): The type of the output. Must be one of the following: "text", "object", "embedding", "segmentation2D", "segmentation3D".  
        value (Union[TextOutput, ObjectOutput, Embedding, ImageSegmentation2D, ImageSegmentation3D]): The value of the output, which can be one of several types.  
        confidence_score (Optional[float]): The confidence score of the output. Defaults to 0.0.  
        description (Optional[str]): A description of the output. Defaults to an empty string.  
    """  

    type: Literal["text", "object", "embedding", "segmentation2d", "segmentation3d"] = Field(  
        ..., description="The type of the output"  
    )  
    value: Union[TextOutput, ObjectOutput, EmbeddingOutput,Segmentation2DOutput] 
    confidence_score: Optional[Union[float, None]] = None  
    description: Optional[str] = None  
    
    def to_dict(self) -> dict:  
        """  
        Converts the EnrichmentOutput instance to a dictionary.  

        Returns:  
            dict: A dictionary representation of the EnrichmentOutput instance.  
        """  
        return self.model_dump()
   