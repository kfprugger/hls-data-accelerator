# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------
from pydantic import BaseModel, Field, model_validator  

class TextSpan(BaseModel):  
    """  
    Attributes:  
        start_position (int): The starting position of the text span.  
        end_position (int): The ending position of the text span.  
    """  

    start_position: int = Field(..., description="The starting position of the text span")  
    end_position: int = Field(..., description="The ending position of the text span")  

    @model_validator(mode='after')  
    def check_positions(cls, values):  
        start_position = values.start_position  
        end_position = values.end_position  
        if start_position > end_position:  
            raise ValueError('end_position must be greater than or equal to start_position')  
        return values  
