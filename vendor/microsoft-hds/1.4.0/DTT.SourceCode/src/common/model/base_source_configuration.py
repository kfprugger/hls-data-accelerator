from typing import FrozenSet, Optional

from pydantic import Field, field_serializer, field_validator
from pyspark.sql.types import DataType

from common.model.data_access_definition import DataAccessDefinition
from common.model.data_type_serializer import DataTypeSerializer
from common.model.data_type_validator import DataTypeValidator
from common.model.immutable_model import ImmutableModel
from common.model.source_to_reference_mapping import SourceToReferenceMapping
from common.model.types import DataSourceId


class BaseTableColumn(ImmutableModel):
    name: str = Field(...)
    type: DataType = Field(...)
    expression: Optional[str] = Field(None)

    @field_validator('type', mode='before')
    @classmethod
    def validate_type(cls, value):
        return DataTypeValidator.validate(value)

    @field_serializer("type")
    def serialize_type(self, value):
        return DataTypeSerializer.serialize(value)


class BaseSourceTableSchema(ImmutableModel):
    columns: FrozenSet[BaseTableColumn] = Field(...)


class CommonSourceConfiguration(ImmutableModel):
    source_id: DataSourceId = Field(...)
    data_access_definition: DataAccessDefinition = Field(...)
    source_to_reference_mappings: FrozenSet[SourceToReferenceMapping] = Field(...)


class BaseSourceConfiguration(CommonSourceConfiguration):
    table_schema: Optional[BaseSourceTableSchema] = Field(None)
