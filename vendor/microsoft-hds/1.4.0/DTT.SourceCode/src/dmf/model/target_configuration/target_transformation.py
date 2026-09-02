import hashlib
from typing import Optional, Union

from pydantic import model_validator, Field, validator, field_serializer
from pyspark.sql.types import DataType

from common.model.immutable_model import ImmutableModel
from common.model.types import DataSourceId, ColumnName
from common.model.data_type_validator import DataTypeValidator
from common.model.data_type_serializer import DataTypeSerializer


class ColumnTransformation(ImmutableModel):
    transformation_target_id: DataSourceId = Field(...)
    owner_target_id: DataSourceId = Field(...)
    original_source_field_name: Optional[str] = Field(None)
    target_field_name: ColumnName = Field(...)
    target_field_type: DataType = Field(...)
    source_field_type: DataType = Field(...)
    target_field_value: Optional[Union[str, float, int, bool]] = Field(None)
    is_source_primary_key: bool = Field(...)
    target_field_condition: Optional[str] = Field(None)
    should_be_id_mapped: bool = Field(...)
    has_source_field: bool = Field(True)

    @validator("target_field_type", pre=True)
    def validate_target_field_type(cls, value):
        return DataTypeValidator.validate(value)

    @validator("source_field_type", pre=True)
    def validate_source_field_type(cls, value):
        return DataTypeValidator.validate(value)

    @field_serializer("target_field_type")
    def serialize_target_field_type(self, value):
        return DataTypeSerializer.serialize(value)

    @field_serializer("source_field_type")
    def serialize_source_field_type(self, value):
        return DataTypeSerializer.serialize(value)

    @model_validator(mode='after')
    def validate_fields(self) -> 'ColumnTransformation':
        if self.target_field_value is not None and self.target_field_condition is not None:
            raise ValueError(f"Cannot have both target_field_value and target_field_condition in {self}")

        if self.target_field_value is not None and not isinstance(self.target_field_value, str):
            raise ValueError(
                f"{self.transformation_target_id}.{self.target_field_name} must be a string, but is {type(self.target_field_value)}")

        if self.target_field_condition is not None and not isinstance(self.target_field_condition, str):
            raise ValueError(
                f"{self.transformation_target_id}.{self.target_field_condition} must be a string, but is {type(self.target_field_condition)}")

        return self

    def _source_column_prefix(self) -> str:
        return f"{self.original_source_field_name}_{self.transformation_target_id}_{self.target_field_name}_"

    @staticmethod
    def _stable_hash(*strings) -> str:
        """takes a list of strings and returns a stable hexadecimal string hash
        """
        return hashlib.sha256("".join(strings).encode("utf-8")).digest().hex()

    @property
    def source_field_name(self) -> str:
        if self.target_field_value is not None:
            field_value_hash = ColumnTransformation._stable_hash(self.target_field_value)
            return f"{self._source_column_prefix()}{field_value_hash}".replace("-", "_")

        elif self.target_field_condition is not None:
            condition_hash = ColumnTransformation._stable_hash(self.target_field_condition)
            return f"{self._source_column_prefix()}{condition_hash}".replace("-", "_")

        else:
            return self.original_source_field_name

    def __str__(self):
        return ("TargetTransformation["
                f"target={self.transformation_target_id}, "
                f"target_field={self.target_field_name}, "
                f"source_field={self.original_source_field_name}, "
                f"{self.source_field_type}->{self.target_field_type}, "
                f"target_calculated_value={self.target_field_value}, "
                f"is_primary_key={self.is_source_primary_key}, "
                f"should_be_id_mapped={self.should_be_id_mapped}, "
                f"source_field_calculated_value={self.source_field_calculated_value}]")
