import json
from enum import Enum
from typing import List, Union

from pydantic import BaseModel, Field, model_validator


class NoExtrasBaseModel(BaseModel):
    class Config:
        extra = "forbid"


class DataFormatEnum(str, Enum):
    parquet = "parquet"
    delta = "delta"


class Table(NoExtrasBaseModel):
    name: str = Field(..., description="Source table name for a query")
    path: str = Field(..., description="Path to file or folder containing the table's data")
    # tableType: DataFormatEnum


class SQLItem(NoExtrasBaseModel):
    tables: List[Table] = Field(..., description="Collection of tables to be used by the query")
    sql: str = Field(..., description="A SQL query to be used for mappings. The query must return columns named sourceKeys, targetKey")


class JSonItem(NoExtrasBaseModel):
    targetKey: int = Field(..., description="The key of a reference data item to be mapped into")
    sourceKeys: List[Union[int, str]] = Field(..., description="A collection of strings or integers to be used to map source reference data values into the target key")


class MappingFileModel(NoExtrasBaseModel):
    """The mapping file contains the needed mapping for a single reference data target file. The file should be named exactly as the target file"""

    jsonSchema_: Union[str, None] = Field(None, description="Reference the json schema to support structural validation", alias="$schema")
    values: List[JSonItem] = Field(None, description="An collection of reference data mappings")
    query: Union[SQLItem, None] = Field(
        None, description="A query defining source of reference data mapping." "The query should return the following columns: target_value, source_value"
    )

    @classmethod
    def from_str(cls, reference_mapping_str: str) -> "MappingFileModel":
        return cls(**json.loads(reference_mapping_str))

    @model_validator(mode="after")
    def validate_values_or_query(self) -> "MappingFileModel":
        if self.values is None and self.query is None:
            raise ValueError("Neither Values nor Query were specified in mapping json file")
        elif self.values is not None and self.query is not None:
            raise ValueError("Either Values or Query must be specified in mapping json file")
        return self
