from typing import List

from configuration_compiler.config_files_models.models_base import NoExtrasBaseModel
from pydantic import Field


class DurationTable(NoExtrasBaseModel):
    table: str = Field(
        ...,
        description="A duration table name. These tables usually present an intersection "
        "tables showing a state in time, with start/end fields",
    )
    startField: str = Field(..., description="The start field of duration table")
    endField: str = Field(..., description="The end field of the duration table")
    groupBy: List[str] = Field([], description="A list of fields to group by")


class TimestampTable(NoExtrasBaseModel):
    table: str = Field(
        ...,
        description="A Timestamp table name. These tables usually represent temporal tables with a "
        "field defining the date and time of a record",
    )
    field: str = Field(..., description="The field defining the date/time of a record")


class ExtensionTable(NoExtrasBaseModel):
    parentTable: str = Field(..., description="The parent table name, e.g. Customer")
    childTable: str = Field(..., description="The child table name, IndividualCustomer")


class ReferenceTable(NoExtrasBaseModel):
    table: str = Field(..., description="Reference table name, e.g., Gender")
    keyField: str = Field(..., description="The key field of a reference table")
    nameField: str = Field(..., description="The default 'name' field of a reference table")
    industries: List[str] = Field([], description="The industries the reference table is used in")


class RawSemanticsModel(NoExtrasBaseModel):
    referenceTables: List[ReferenceTable] = Field([], description="A collection of reference tables of an industry")
    durationTables: List[DurationTable] = Field([], description="A collection of duration tables of industry")
    timestampTables: List[TimestampTable] = Field([], description="A collection of timestamp tables of an industry")
    extensionTables: List[ExtensionTable] = Field([], description="A collection of extension tables")
