from typing import List, Optional

from configuration_compiler.config_files_models.models_base import FieldTypeEnum, NoExtrasBaseModel
from pydantic import Field


class PartitionRule(NoExtrasBaseModel):
    name: str = Field(..., description="The name of the partition field, e.g., prYear")
    fields: List[str] = Field(
        ...,
        description="A collection of table.field names, specifying a field on which the partition is based",
    )
    rule: str = Field(
        ...,
        description="A partition rule. Define a spark sql expression using {} as a placeholder for the field to be partitioned by, e.g., year({}) will "
        "return the year for a field specified in the 'fields' collection",
    )
    type: FieldTypeEnum = Field(..., description="The type of the partition field")
    enabled: Optional[bool] = Field(True, description="Defines if this rule should apply to the partition field")


class PartyType(NoExtrasBaseModel):
    type: str = Field(..., description="The party type as defined in the PartyType reference table.")
    table: str = Field(
        ...,
        description="The name of the table that should be used. DMF will use the party type to determine the table to be used",
    )


class PKGroup(NoExtrasBaseModel, extra="allow"):
    group: str = Field(
        ...,
        description="The group name will be used to define the mapping table for the group",
    )
    tables: List[str] = Field(..., description="A collection of tables in the group")


class RawSemanticsConfigModel(NoExtrasBaseModel):
    partitionRules: List[PartitionRule] = Field([], description="A collection of partition rules")
    statusTables: List[str] = Field(
        [],
        description="A collection of status table. A change in the status field in an anchor table (e.g, contact) will apply to all duration "
        "tables except the status table, e.g., CustomerStatus ",
    )
    partyTables: List[str] = Field([], description="A collection of all tables acting as party, e.g., Party in IDM")
    partyTypes: List[PartyType] = Field([], description="A collection of tables with their assigned party type name")
    pkGroups: List[PKGroup] = Field(
        [],
        description="Primary key Groups define a unified mapping for a collection of tables",
    )
