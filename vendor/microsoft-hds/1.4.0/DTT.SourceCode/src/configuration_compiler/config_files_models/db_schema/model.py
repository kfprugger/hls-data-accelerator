from enum import Enum
from typing import Any, List, Optional

from configuration_compiler.config_files_models.models_base import (FieldTypeEnum,
                                                      NoExtrasBaseModel)
from pydantic import Field, Json, field_validator


class EntityTypeEnum(str, Enum):
    table = "TABLE"


class TableTypeEnum(str, Enum):
    table = "EXTERNAL"


class Namespace(NoExtrasBaseModel):
    databaseName: str = Field(..., description="Industry database model name")


class JoinPair(NoExtrasBaseModel):
    fromAttribute: str
    toAttribute: str


class RelationShip(NoExtrasBaseModel):
    joinPairs: List[JoinPair]
    fromEntity: str
    toEntity: str

    @field_validator("fromEntity", mode="before")
    @classmethod
    def split_fromEntity(cls, input):
        return input.rsplit("/", 1)[-1]

    @field_validator("toEntity", mode="before")
    @classmethod
    def split_toEntity(cls, input):
        return input.rsplit("/", 1)[-1]


class FieldProperties(NoExtrasBaseModel):
    minValue: Optional[Any] = Field(None, description="Min value of a numeric field")
    maxValue: Optional[Any] = Field(None, description="Max value of a numeric field")
    description: str = Field(..., description="Description of a field")
    dateFormat: Optional[str] = Field(None, description="Date format of a field")
    timestampFormat: Optional[str] = Field(
        None, description="Timestamp format of a field"
    )


class OriginDataTypeName(NoExtrasBaseModel):
    typeName: FieldTypeEnum = Field(..., description="Field type")
    isNullable: bool = Field(..., description="Is it allowed for the field to be null")
    properties: Optional[FieldProperties] = Field(
        None, description="Properties of the field"
    )
    length: Optional[int] = Field(None, description="The length of a string field")
    precision: Optional[int] = Field(None, description="The precision of a float field")
    scale: Optional[int] = Field(None, description="The scale of a float field")


class Column(NoExtrasBaseModel):
    name: str = Field(..., description="The field name")
    originDataTypeName: OriginDataTypeName = Field(..., description="Field properties")


class StorageDescriptor(NoExtrasBaseModel):
    columns: List[Column] = Field(..., description="Collection of fields")


class TableProperties(NoExtrasBaseModel):
    businessArea: str = Field(..., description="Table business area of the table")
    path: str = Field(..., description="CDM table path")
    description: str = Field(..., description="Table description")
    displayName: str = Field(
        ..., description="Table display name. Can be used by Power BI"
    )
    isDay0Entity: str
    fromBusinessAreas: str
    primaryKeys: Optional[List[str]] = Field(
        None,
        description="The primary keys of a Table. Table can have multiple fields as primary keys",
    )
    industries: str = Field(..., description="Industries of a table")
    relationships: Optional[Json[List[RelationShip]]] = Field(
        None,
        description="Relationships between foreign keys of the current table to primary keys in other tables",
    )

    @field_validator("primaryKeys", mode="before")
    @classmethod
    def split_arg(cls, input):
        return [pk.strip() for pk in input.split(",")]


class ModelItem(NoExtrasBaseModel):
    namespace: Namespace
    tableType: TableTypeEnum = Field(..., description="The table type")
    storageDescriptor: StorageDescriptor = Field(
        ..., description="Collection of fields"
    )
    name: str = Field(..., description="The table name")
    entityType: EntityTypeEnum = Field(..., description="The entity type")
    properties: TableProperties = Field(..., description="Properties of a table")


class RawSchemaModel(NoExtrasBaseModel):
    tables: List[ModelItem] = Field(..., description="Collection of tables")
