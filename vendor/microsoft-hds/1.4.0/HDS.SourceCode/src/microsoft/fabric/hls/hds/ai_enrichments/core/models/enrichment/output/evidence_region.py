# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------
from typing import Any, Optional
from pydantic import BaseModel
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.text_span import TextSpan


class EvidenceRegion(BaseModel):  
    """
    Represents a region of evidence in various formats such as text, image bounding box, 
    and image segmentation.

    Attributes:
        metadata (Any): Additional metadata associated with the evidence region.
        text_span (Optional[TextSpan]): The span of text that represents the evidence.
        image_bounding_box (Optional[ImageBoundingBox]): The bounding box of the evidence in an image.
        image_segmentation_2d (Optional[ImageSegmentation2D]): The 2D segmentation of the evidence in an image.
        image_segmentation_3d (Optional[ImageSegmentation3D]): The 3D segmentation of the evidence in an image.
    """
    metadata: Any = None  
    text_span: Optional[TextSpan] = None  
    image_bounding_box: Optional[Any] = None  
    image_segmentation_2d: Optional[Any] = None  
    image_segmentation_3d: Optional[Any] = None  