# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------

from typing import Dict, List, Optional, Union
from pydantic import BaseModel, Field


class SegmentationMask(BaseModel):
    background:int = Field(0, description="Background class label.")
    rle: Optional[Union[List[int], str]] = Field(None, description="run-length encoding for class and pixel count.")
    class_label: Optional[Union[List[int], str]] = Field(None, description="2D array of class labels.")