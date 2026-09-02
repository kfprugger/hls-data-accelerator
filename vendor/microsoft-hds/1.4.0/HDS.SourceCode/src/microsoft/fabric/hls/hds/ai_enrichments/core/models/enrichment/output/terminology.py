# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------
from typing import Optional
from pydantic import BaseModel, Field, field_validator  

class Terminology(BaseModel):  
    """  
    A model representing a terminology entry.  

    Attributes:  
        value (str): The value of the terminology entry.  
        name (str): The name of the terminology entry.  
        system (str): The system associated with the terminology entry.  
    """  

    value: str = Field(..., description="Code value in the given coding")  
    name: str = Field(..., description="Coding system name e.g. ICD-10.")  
    system: Optional[str] = Field(None, description="System URI")  
    
    @field_validator('value')  
    def validate_value(cls, value):  
        if not value.strip():  
            raise ValueError('value must not be empty or whitespace')  
        return value  

    @field_validator('name')  
    def validate_name(cls, name):  
        if not name.strip():  
            raise ValueError('name must not be empty or whitespace')  
        return name