# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------
from typing import Dict, Optional
from pydantic import BaseModel, Field, model_validator
from microsoft.fabric.hls.hds.ai_enrichments.core.errors.enrichment_value_error import EnrichmentValueError
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.types.segmentation.segmentation_bounding_box import SegmentationWithBoundingBox
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.types.segmentation.segmentation_mask import SegmentationMask


class Segmentation2DOutput(BaseModel):
    segmentation_mask: Optional[SegmentationMask] = None
    bounding_box: Optional[SegmentationWithBoundingBox] = None
    height: int = Field(..., description="Height of the segmentation.")
    width: int = Field(..., description="Width of the segmentation.")
    metadata: Dict = Field(..., description="Additional metadata.")

    @model_validator(mode="after")
    def validate_fields(cls, values):
        if not (values.segmentation_mask or values.bounding_box):
            raise EnrichmentValueError("Provide either a segmentation mask or bounding box.")
        return values