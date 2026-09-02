import json
from typing import Any, Dict, List

from pydantic import BaseModel, model_validator


class FieldMapping(BaseModel):
    adrmFieldName: str
    referenceFieldName: str


class DataFileModel(BaseModel):
    adrmTableName: str
    fieldMapping: List[FieldMapping]
    data: List[Dict[str, Any]]

    @model_validator(mode="after")
    def check_data_fields_are_defined_in_mapping(self) -> "DataFileModel":
        expected_keys = [field.referenceFieldName for field in self.fieldMapping]
        errors = []
        for idx, row in enumerate(self.data):
            for key in row.keys():
                if key not in expected_keys:
                    errors.append((idx, key))
        if errors:
            msg = "\n".join([f"Row [{idx}]: '{key}' is not defined as a fieldMapping.referenceFieldName" for idx, key in errors])
            raise ValueError(msg)
        return self

    @classmethod
    def from_str(cls, reference_data_str: str) -> "DataFileModel":
        return cls(**json.loads(reference_data_str))
