from typing import Optional

from configuration_compiler.config_files_models.models_base import FieldTypeEnum, NoExtrasBaseModel
from pydantic import Field


class ConfigField(NoExtrasBaseModel):
    name: str = Field(..., description="The field name to add to the collection of tables")
    description: str = Field(
        ...,
        description="The description of the field to be added to the collection of tables",
    )
    tables: list[str] = Field(..., description="Collection of tables to add the field to")
    type: FieldTypeEnum = Field(..., description="The type of the field to be added to the collection of tables")
    length: Optional[int] = Field(
        None,
        description="The length of the string field to be added to the collection of tables",
    )
    enabled: Optional[bool] = Field(True, description="Define if the field will be added to the collection")
    timestampFormat: Optional[str] = Field(
        None,
        description="The timestamp format of the field to be added to the collection of tables",
    )
    scale: Optional[int] = Field(
        None,
        description="The scale  of the field to be added to the collection of tables",
    )
    precision: Optional[int] = Field(
        None,
        description="The scale of the field to be added to the collection of tables",
    )


class PartitionField(NoExtrasBaseModel):
    name: str = Field(
        ...,
        description="The name of the partition field to be added to the collection of tables",
    )
    description: str = Field(
        ...,
        description="The description of the partition field to be added to the collection of tables",
    )
    tables: list[str] = Field(..., description="The collection of tables the partition field will be added to")
    type: FieldTypeEnum = Field(
        ...,
        description="The type of the partition field to be added to the collection of tables",
    )
    partition: bool
    order: int = Field(
        ...,
        description="The order of the partition field to be added to the collection of tables. Field with lower order will be added before field with "
        "higher order, e.g., prYear (order=30) will be added before prMonth (order=40)",
    )
    enabled: Optional[bool] = Field(
        True,
        description="Defines if the partition field will be added to the collection of tables",
    )


class PrimaryKeyConfig(NoExtrasBaseModel):
    add: Optional[list[str]] = Field([], description="Collection of fields to be added as primary keys")
    remove: Optional[list[str]] = Field([], description="Collection of fields to be removed as primary keys")
    replace: Optional[dict[str, str]] = Field(
        {},
        description="dictionary from a field name to a new field name to be replaced as primary keys",
    )


class PrimaryKey(NoExtrasBaseModel):
    config: PrimaryKeyConfig = Field(
        ...,
        description="configuration of how th primary keys of the table should be changed",
    )
    table: str = Field(..., description="The table to which the primary key will be applied to")


class ReferenceTableRange(NoExtrasBaseModel):
    table: str = Field(
        ...,
        description="For specific reference tables, define the range that will be deployed to the customer in the deployment phase, and will be added to "
        "an existing reference table if exists",
    )
    valueRanges: list[str] = Field(
        ...,
        description="The ranges to be deployed to the customer. May contain either contributors names, or explicit values or value range, "
        "e.g., Shared,5,7,100-200",
    )
    default: bool = Field(
        None,
        description="If true, the range defined here will apply by default to all reference table defined in the semantics file, Except those that are explicitly defined "
        "in the collection",
    )


class ExcludedFields(NoExtrasBaseModel):
    exclude: list[str] = Field([], description="Collection of fields to be excluded from the table")


class DBConfigExtra(NoExtrasBaseModel):
    modifiedOnTargetField: str = Field(
        ...,
        description="The field to be added to the table to store the last modified date of the record on the target",
    )
    sourceTableField: str = Field(
        ...,
        description="The field to be added to the table to store the source table name of the record",
    )


class RawDBConfigModel(NoExtrasBaseModel):
    fields: list[ConfigField] = Field([], description="Collection of fields to add to selected tables")
    tables: dict[str, ExcludedFields] = Field(
        {},
        description="dictionary from a table name to fields that should be excluded from it",
    )
    partitionFields: list[PartitionField] = Field(
        [], description="Collection of partition fields to add to selected tables"
    )
    primaryKeys: list[PrimaryKey] = Field([], description="Collection of primary key fields to add to selected tables")
    referenceTableRanges: list[ReferenceTableRange] = Field(
        [],
        description="Define the default ranges to be applied to all reference table defined in semantics, and for specific reference tables a selected ranges to deploy to "
        "a customer",
    )
    configuration: DBConfigExtra = Field(..., description="Extra configuration for the DBConfigRawModel")
    synapseDBTemplateName: Optional[str] = Field(
        None, description="The name of the template to be used in ADRM Synapse DB"
    )
    jsonSchema_: str = Field(
        None,
        description="The schema version of the model. Used externally",
        alias="$schema",
    )
