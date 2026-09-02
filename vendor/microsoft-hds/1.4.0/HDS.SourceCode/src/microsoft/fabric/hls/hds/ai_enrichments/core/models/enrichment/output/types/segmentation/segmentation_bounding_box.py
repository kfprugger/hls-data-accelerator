# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------

from typing import List, Union, Dict
from pydantic import BaseModel, Field


class SegmentationWithBoundingBox(BaseModel):
    bounding_box: Dict = Field(..., description="Mask bounding box coordinates.")
    metadata: Dict[str, Union[str, int, float, List, Dict]] = Field(..., description="Additional metadata.")
