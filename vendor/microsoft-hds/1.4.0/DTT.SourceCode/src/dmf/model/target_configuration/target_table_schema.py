from typing import FrozenSet, Optional, Tuple

from common.model.base_source_configuration import BaseTableColumn
from pydantic import Field, model_validator, validator, field_serializer

from common.model.immutable_model import ImmutableModel
from common.model.types import DataSourceId, TargetId
from common.model.data_type_validator import DataTypeValidator
from common.model.data_type_serializer import DataTypeSerializer


class ForeignKey(ImmutableModel):
    from_attribute: str = Field(...)
    to_attribute: str = Field(...)

    def __str__(self) -> str:
        return f"FK[{self.from_attribute}->{self.to_attribute}]"

    def __repr__(self) -> str:
        return self.__str__()


class TableRelation(ImmutableModel):
    foreign_keys: Tuple[ForeignKey, ...] = Field(...)
    from_entity: DataSourceId = Field(...)
    to_entity: DataSourceId = Field(...)

    def __str__(self) -> str:
        return f"TableRelation[{self.from_entity}->{self.to_entity}, fks={self.foreign_keys}]"

    def __repr__(self) -> str:
        return self.__str__()


class TableColumn(BaseTableColumn):
    name: str = Field(...)
    is_nullable: bool = Field(...)

    @validator("type", pre=True)
    def validate_type(cls, value):
        return DataTypeValidator.validate(value)

    @field_serializer("type")
    def serialize_type(self, value):
        return DataTypeSerializer.serialize(value)\



class TargetTableColumn(TableColumn):
    is_primary_key: bool = Field(...)


class DurationTableSemantics(ImmutableModel):
    name: str = Field(...)
    start_col_name: str = Field(...)
    end_col_name: str = Field(...)
    group_by_cols: FrozenSet[str] = Field(default_factory=frozenset)


class TargetTableSchema(ImmutableModel):
    id: TargetId = Field(...)
    relations: FrozenSet[TableRelation] = Field(...)
    columns: FrozenSet[TargetTableColumn] = Field(...)
    db: DataSourceId = Field(...)
    is_ref_table: bool = Field(False)
    is_duration_table: bool = Field(False)
    duration_semantics: Optional[DurationTableSemantics] = Field(None)

    @model_validator(mode="after")
    def check_values(self):
        if self.is_ref_table and self.is_duration_table:
            raise ValueError(f"Table {self.id} cannot be both reference and duration table")
        return self

    @property
    def column_names(self) -> FrozenSet[str]:
        return frozenset([column.name for column in self.columns])
