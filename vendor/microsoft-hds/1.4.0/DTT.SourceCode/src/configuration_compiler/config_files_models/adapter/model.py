import re
from enum import Enum
from typing import Any, Optional, Union

from configuration_compiler.config_files_models.models_base import FieldTypeEnum, NoExtrasBaseModel
from pydantic import Field, field_validator
from pydantic.functional_validators import model_validator


class DataFormatEnum(str, Enum):
    parquet = "parquet"
    delta = "delta"
    csv = "csv"


class DeleteBehaviorEnum(str, Enum):
    hard = "hard"
    soft = "soft"
    de_id = "de-id"


class Storage(NoExtrasBaseModel):
    dataFormat: Optional[DataFormatEnum] = Field(None, description="The format of data in storage, e.g., delta.")
    connectionStringUri: Optional[str] = Field(
        None,
        description="The path to the root folder of the data in storage, or a path to a file describing for each table a different path.",
    )
    lakeDBName: Optional[str] = Field(
        None,
        title="Source Lakehouse name",
        description="When Fabric Lakehouse is used as a source, the lakeDBName will be used as the source database name, e.g., a Fabric Lakehouse name."
        "\nIn this case the environment file should not contain a source section",
    )


class PKInternalExternalPair(NoExtrasBaseModel):
    internalField: str = Field(
        ...,
        title="Internal field",
        description="The internal field that is used as PK, e.g., contactid.")
    externalField: str = Field(
        ...,
        title="External field",
        description="The external field that is used as keyring between multiple data sources, e.g., integrationKey.",
    )


class QueryTable(NoExtrasBaseModel):
    name: str = Field(..., description="A table name that is used in a source query, e.g., in a join.")
    alias: Optional[str] = Field(None, description="An alias to be used in the source query for that table.")


class TargetAnchorTable(NoExtrasBaseModel):
    tableName: str = Field(
        ...,
        title="Target anchor table",
        description="A target table which the source writes to its single PK field.")


class IntermediateTable(NoExtrasBaseModel):
    intermediateTable: str = Field(
        ...,
        description="Table that is used by DMF to create a relationship graph between anchor table and a target table.",
    )


class TargetTable(NoExtrasBaseModel):
    targetTable: str = Field(..., description="An anchor table.")
    intermediateTables: list[IntermediateTable] = Field(
        ...,
        title="Target table",
        description="Collection of tables in the graph between an anchor table and the last table in the collection.",
    )


class TargetField(NoExtrasBaseModel):
    enabled: Optional[bool] = Field(
        True,
        title="Target field",
        description="A flag to indicate if the target field should be processed by DMF and validated in the DTT VS Extension.",
    )
    tableName: str = Field(
        ...,
        title="Goal table name",
        description="The table DMF uses to decide what table(s) to write to. "
        "\nIf the source field is a FK, The tableName should NOT be the real target table, "
        "but either a reference table or a regular table that the FK relates to. "
        "\nThen, the fieldName should be the PK field of that table. "
        "\nDMF will find the actual tables and fields to write to, "
        "by searching for valid table paths from anchor tables to tableName, "
        "e.g., 'contact.maritalstatusstate' target should be 'MaritalStatus.MaritalStatusId'. "
        "\nIn all other cases, the target table should be the real target table.",
    )
    fieldName: str = Field(
        ...,
        title="Goal field",
        description="The name the field in the target table.")
    condition: Optional[str] = Field(
        None,
        title="Condition",
        description="The target field will be processed if the condition, a Spark SQL scalar expression evaluates to true.",
    )
    fieldValue: Optional[Union[str, float, int, bool]] = Field(
        None,
        title="Field value",
        description="When specified, the Spark SQL expression will be evaluated and used instead of the source field value.",
    )
    targetField: Optional[str] = Field(
        None,
        title="Target field",
        description="When the source field is a FK and the tableName specified is a FK related table (e.g. Customer), "
        "\nnthen, DMF resolves the actual tables and fields to write to, "
        "it may find ambguities that require additional information from the author, e.g., "
        "a RelatedCustomer table has two FK to Customer (from, to). "
        "In this case, the author should specify the target field name in the target table, e.g., 'FromCustomerId'.",
    )
    paths: Optional[list[str]] = Field(
        None,
        title="Paths",
        description="In the rare cases in which DMF cannot decipher a non ambiguous graph path, the adapter should provide the correct path.",
    )
    _paths_split_pattern = re.compile(r"<-|->")

    description: Optional[str] = Field(
        None,
        title="Description",
        description="A description of the target field.")
    # TODO: remove? isLookup is currently not used
    isLookup: Optional[bool] = Field(False, description="A flag to indicate that the target field is a lookup field")

    @field_validator("paths", mode="before")
    @classmethod
    def split(cls, s):
        if s is None:
            return None
        if not re.search(cls._paths_split_pattern, s):
            raise ValueError(f"paths {s} should contain at least one '<-' or '->' arrow")
        return re.split(cls._paths_split_pattern, s)

    @field_validator("paths", mode="after")
    @classmethod
    def path_len_is_more_than_1(cls, paths):
        if paths is None:
            return None
        for path in paths:
            if len(path) < 2:
                raise ValueError("paths should have more than one table")
        return paths

    @model_validator(mode="after")
    def field_value_and_condition_mutually_exclusive(self) -> "TargetField":
        if not self.enabled:
            return self
        condition = self.condition
        fieldValue = self.fieldValue
        if condition and fieldValue:
            raise ValueError(
                f"Cannot define both 'fieldValue' and 'condition' properties for a target field:"
                f"'{self.fieldName}' in table '{self.tableName}' in the adpater file. fieldValue='{fieldValue}', condition='{condition}'"
            )
        return self


class UniqueKeyItem(NoExtrasBaseModel):
    fieldName: str = Field(
        ...,
        description="A target field name that is part of the uniquely collection of target fields.",
    )


class TargetFields(NoExtrasBaseModel):
    fields: list[TargetField] = Field(
        None,
        title="Target fields",
        description="A collection of target fields which may be in multiple tables."
    )
    uniqueKey: Optional[list[UniqueKeyItem]] = Field(
        None,
        description="A collection of some target fields that defines the uniqueness of record to be written, e.g., create "
        "history records for each email type (work/home).",
    )


class SourceField(NoExtrasBaseModel):
    fieldName: str = Field(
        ...,
        title="Source field",
        description="A source field name or a calculation name. A Calculation name should not be an existing field name.",
    )
    fieldType: FieldTypeEnum = Field(
        ...,
        title="Source field type",
        description="The source field type.")
    enabled: Optional[bool] = Field(
        True,
        title="Enabled",
        description="Defines whether DMF should process the field or skip it. \nAlso, whether the DTT VS Extension should validate the field.",
    )
    targetFields: TargetFields = Field(
        ...,
        title="Target fields",
        description="The Fields the data is written to. A source field may write to multiple target fields in different tables.",
    )
    fieldCalculatedValue: Optional[str] = Field(
        None,
        title="Calculated field",
        description="A spark SQL scalar expression.")
    description: Optional[str] = Field(
        None,
        title="Description",
        description="A description of the source field.")
    enforceKeyHarmonization: Optional[bool] = Field(
        False,
        title="Enforce field value harmonization",
        description="Set the property to true when:\n"
        "\t1. bypassHarmonization property on the parent table is set to True\n"
        "\t2. There is a  need for DMF to override the table definition and harmonize "
        "the current field, e.g., a field was introduced in a query (based on the "
        "parent table) so it should not be bypassed",
    )


class SourceTable(NoExtrasBaseModel):
    """Source table to map into target"""

    description: Optional[str] = Field(
        None,
        title="Source table description",
        description="A description of the source table.")
    tableName: str = Field(
        ...,
        title="Source table name",
        description="The name of the source table. If query is defined, "
        "the name provides additional semantics and cannot be the same as an existing table.",
    )
    query: Optional[str] = Field(
        None,
        title="Source query",
        description="Spark SQL query to use as a source, .e.g., performing join with between two or more tables. The result fields "
        "can be mapped to target tables and fields..",
    )
    modifiedonField: str = Field(
        ...,
        title="Modified field",
        description="The field used to identify data updates when performing incremental updates.",
    )
    stateField: Optional[str] = Field(
        None,
        title="State field",
        description="The field used to identify state changes, e.g., customer becomes inactive/active.",
    )
    deletedField: Optional[str] = Field(
        None,
        title="Deleted field",
        description="The field used to identify that record was deleted in the source system.",
    )
    deleteBehavior: Optional[DeleteBehaviorEnum] = Field(
        None,
        title="Deleted behavior",
        description="Delete behavior defines whether to hard delete these records\\tag them as deleted\\tag as deleted "
        "and de-id target fields.",
    )
    targetAnchorTables: list[TargetAnchorTable] = Field(
        ...,
        title="Target anchor tables",
        description="Target Tables to be used as anchors. A source table can have multiple target anchor tables, "
        "e.g., contact->Customer, Location. "
        "\nDMF will resolve all valid tables paths from anchor tables to all target tables "
        "and write to intermeidate tables as needed.",
    )
    pkInternalExternalPairs: list[PKInternalExternalPair] = Field(
        [],
        title="Internal/External field pairs",
        description="Field pairs that define strong relationship between two field, .e.g contactId and intergrationKey "
        "defined respectively, specify that the same mapping value (number) created for the integrationKey (string) will be "
        "used also for contactId.",
    )
    enabled: Optional[bool] = Field(
        True,
        title="Enabled",
        description="Defines whether DMF will process all fields in this table or skip them. "
        "\nAlso, whether the DTT VS Extension should validate the table and its source fields.",
    )
    sourceFields: list[SourceField] = Field(
        ...,
        title="Source fields",
        description="Collection of source fields to be processed.")
    bypassKeysHarmonization: Optional[bool] = Field(
        False,
        title="Bypass PK/FK values harmonization",
        description="When set to True, DMF will use, as is, values that are mapped "
        "to PK/FKs in target tables (with no harmonization).\nApplies to both target "
        "standard tables and reference tables",
    )

    @model_validator(mode="after")
    def paths_mis_definition(self) -> "SourceTable":
        if not self.enabled:
            return self
        paths_by_target_table = {}
        for source_field in self.sourceFields:
            if not source_field.enabled:
                continue
            for target_field in source_field.targetFields.fields:
                if not target_field.enabled:
                    continue
                paths = target_field.paths
                if paths:
                    if target_field.tableName in paths_by_target_table:
                        raise ValueError(
                            f"paths are defined for target table {target_field.tableName} more than once in source table {self.tableName}"
                        )
                    paths_by_target_table[target_field.tableName] = paths

        return self

    @model_validator(mode="after")
    def validate_paths_have_valid_tables(self) -> "SourceTable":
        if not self.enabled:
            return self
        anchors = [anchor.tableName for anchor in self.targetAnchorTables]
        for source_field in self.sourceFields:
            if not source_field.enabled:
                continue
            for target_field in source_field.targetFields.fields:
                if not target_field.enabled:
                    continue
                paths = target_field.paths
                if paths:
                    paths_anchors = []
                    for path in paths:
                        anchor_table, target_table = path[0], path[-1]
                        if anchor_table not in anchors:
                            raise ValueError(
                                f"first table {anchor_table} in path {path} is not defined as a target anchor table in source table {self.tableName}"
                            )
                        if target_table != target_field.tableName:
                            raise ValueError(
                                f"last table {target_table} in path {path} is not the same as the target table {target_field.tableName} in source table {self.tableName}"
                            )
                        paths_anchors.append(anchor_table)

                    if len(paths_anchors) != len(set(paths_anchors)):
                        raise ValueError(
                            f"paths {paths} in source table {self.tableName} should have only one path for every anchor table"
                        )
        return self


def json_schema_extra(schema: dict[str, Any], model) -> None:
    for prop in schema.get("properties", {}).values():
        prop.pop("title", None)


class RawAdapterModel(NoExtrasBaseModel, json_schema_extra=json_schema_extra):
    name: str = Field(...,
                      title="Adapter name",
                      description="The adapter name defines the data source, e.g. Healthcare-Dataverse."
                      "\n1. It is used internally to associate a source table's external/external ID mapping columns to a specific source."
                      "\n2. It is part of the SourceTable lineage column that DMF adds to each target table.")
    description: str = Field(
        "",
        title="Adapter description",
        description="Description of the adapter")
    version: str = Field(
        ...,
        title="Adapter version",
        description="Version of the adapter")
    sourceDomain: str = Field(
        "",
        title="Source name",
        description="Defines the sourceDomain to be used for reference data mappings (e.g., Healthcare-Dataverse)."
        "\nWhen 'reference data mapping update' API is called,"
        "\nusing the current adapter, the associated source schema, and a collection of mapping folders (i.e., Industry\\Source, Customer\\Source) relaing to the source,"
        "\nit will use the sourceDomain as the name of the collected mappings."
        "\nThen, when DMF transforms data and resolves reference values,"
        "\nit will first filter the reference data mapping table by the source domain,"
        "\nto make sure only relevant mapping values for the current data source are used.",
    )
    source: Optional[Storage] = Field(None, description="Source data storage")
    target: Optional[Storage] = Field(None, description="Target data storage")
    dbSourceSchema: Optional[str] = Field(
        None,
        title="Source schema",
        description="Source schema file path (tables/fields names/types/descriptions)."
        "\nIf the property is missing or empty, VS Code will use 'dbSourceSchema.json' file in the adapter's folder"
        "\nThe file is used for validation and auto-complete of source related properties"
    )
    dbTargetSchema: Optional[str] = Field(
        None,
        title="Target schema",
        description="Target schema file path (tables/fields names/types/descriptions, relationships and primary keys...)."
        "\nIf the property is missing or empty, VS Code will use 'dbTargetSchema.json' file in the adapter's folder"
        "\nThe file is used for validation and auto-complete of target related properties"
    )
    dbTargetSchemaConfig: Optional[str] = Field(
        None,
        title="Target schema configuration",
        description="Target schema config file path."
        "\nIf the property is missing or empty, VS Code will use 'dbTargetSchemaConfig.json' file in the adapter's folder"
        "\nThe file defines operational fields (e.g., partitions) DTT will add to target tables"
    )
    dbSemantics: Optional[str] = Field(
        None,
        title="Target semantics",
        description="Target semantics file path."
        "\nIf the property is missing or empty, VS Code will use 'dbTargetSemantics.json' file in the adapter's folder"
        "\nThe file provides additonal semantics to the target tables, e.g., what tables are reference tables, duration tables..."
    )
    dbSemanticsConfig: Optional[str] = Field(
        None,
        title="Target semantics configuration",
        description="Target semantics config file path."
        "\nIf the property is missing or empty, VS Code will use 'dbTargetSemanticsConfig.json' file in the adapter's folder"
        "\nThe file provides additonal operational semantics to the target tables, e.g., what are the partitions field's expression..."
    )
    dmfEnvConfig: Optional[str] = Field(
        None,
        title="Envrionment",
        description="Environment file path."
    )
    defaultReferenceValue: Optional[Union[int, None]] = Field(
        None,
        title="Default reference value",
        description="When reference value is not found during transformation "
        "\nand 'UponMissingReferenceValues' is false, DMF will use this value instead .",
    )
    failUponMissingReferenceValues: bool = Field(
        False,
        title="Missing reference value failure behavior",
        description="If false, DMF will fail during transformation when a reference value is missing in the mapping table. "
        "\nIf true, DMF will use the defaultReferenceValue instead.",
    )
    queryTables: list[QueryTable] = Field(
        [],
        description="Tables used in source tables queries, e.g., when joining two or more tables. Optional, "
        "relevant only if the source is defined as an ADLS storage and not as a Database "
        "Database may be a Fabric Lakehouse.",
    )
    sourceTables: list[SourceTable] = Field(
        ...,
        title="Source tables",
        description="Tables and fields mappings between source and target.")
    jsonSchema_: str = Field(
        "",
        title="Adapter schema definition",
        description="The json schema of the adapter. Used by the DTT VS Extension to validate and autocomplete the adapter properties",
        alias="$schema",
    )
