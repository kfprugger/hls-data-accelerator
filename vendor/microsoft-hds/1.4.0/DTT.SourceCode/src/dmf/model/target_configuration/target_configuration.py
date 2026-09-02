from typing import FrozenSet, Optional

from pydantic import Field, field_serializer, validator
from pyspark.sql.types import DataType

from common.model.data_access_definition import DataAccessDefinition
from common.model.immutable_model import ImmutableModel
from common.model.types import FeedId, TargetId
from dmf.model.target_configuration.target_table_schema import TargetTableSchema
from dmf.model.target_configuration.target_transformation import ColumnTransformation
from common.model.data_type_validator import DataTypeValidator
from common.model.data_type_serializer import DataTypeSerializer


class PartitionConfig(ImmutableModel):
    input_col_name: str = Field(...)
    partition_col_name: str = Field(...)
    input_col_to_partition_col_rule: str = Field(...)
    partition_col_type: DataType = Field(...)

    @validator("partition_col_type", pre=True)
    def validate_type(cls, value):
        return DataTypeValidator.validate(value)

    @field_serializer("partition_col_type")
    def serialize_type(self, value):
        return DataTypeSerializer.serialize(value)


class TemporalColumns(ImmutableModel):
    start_col_name: str = Field(...)
    end_col_name: str = Field(...)


class ReferenceTableSemantics(ImmutableModel):
    name: str = Field(...)
    key_field: str = Field(...)
    name_field: str = Field(...)


class TargetConfiguration(ImmutableModel):
    feed_id: FeedId = Field(...)
    target_id: TargetId = Field(...)
    data_access_definition: DataAccessDefinition = Field(...)
    target_columns_transformations: FrozenSet[ColumnTransformation] = Field(...)
    partitions_config: FrozenSet[PartitionConfig] = Field(...)
    temporal_tables_semantics: Optional[TemporalColumns] = Field(None)
    table_schema: Optional[TargetTableSchema] = Field(None)
    target_modified_date_column_name: str = Field(...)

    def __str__(self) -> str:
        return f"TargetConfiguration[data={self.data_access_definition}"
