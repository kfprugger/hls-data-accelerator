# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------
from pydantic import BaseModel

class EnrichmentViewExpression(BaseModel):
    """
    EnrichmentViewExpression is a data model representing an query for data extraction.
    """
    # Type of the enrichment view expression
    type: str = "sql"
    # Query associated with the enrichment view expression
    query: str= ""

    # Method to convert the model instance to a dictionary
    def to_dict(self) -> dict:
        # Use Pydantic's model_dump method to generate a dictionary representation
        return self.model_dump()

