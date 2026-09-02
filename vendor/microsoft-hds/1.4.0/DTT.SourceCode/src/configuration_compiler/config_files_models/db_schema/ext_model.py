import json
from typing import Any, Optional

import pydantic
from configuration_compiler.config_files_models.common.field_type import CommonParsing, FieldParsingExtraProps
from configuration_compiler.config_files_models.db_schema.model import JoinPair, ModelItem, RawSchemaModel, RelationShip
from configuration_compiler.config_files_models.semantics.ext_model import SemanticsModel
from configuration_compiler.config_files_models.utils.duration_table_semantics_utils import from_DurationTable
from configuration_compiler.spec_models.target_table_schema import TargetTableSchemaExt, TargetTableColumnExt
from common.model.types import DataSourceId
from dmf.model.target_configuration.target_table_schema import ForeignKey, TableRelation


class DBSchemaModel(RawSchemaModel, extra="allow"):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.__tables_dict = None
        self.__pointed_tables_of_field_cache = {}

    @classmethod
    def from_str(cls, db_schema: str) -> "DBSchemaModel":
        type_adapter = pydantic.TypeAdapter(list[ModelItem])
        try:
            tables = type_adapter.validate_json(db_schema)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse target DB schema: {e}")
        return cls(tables=tables)

    @property
    def tables_dict(self) -> dict[str, ModelItem]:
        if self.__tables_dict is None:
            self.__tables_dict = {table.name: table for table in self.tables}
        return self.__tables_dict

    def _get_pointing_tables(self, pointed_table_name: str) -> list[ModelItem]:
        pointing_tables = []
        for table in self.tables:
            for rel in table.properties.relationships:
                if rel.toEntity == pointed_table_name:
                    pointing_tables.append(table)
        return pointing_tables

    def _get_pointing_tables_on_field(self, pointed_table_name: str, pointed_field_name: str) -> list[ModelItem]:
        cache_key = f"{pointed_table_name}.{pointed_field_name}"
        if cache_key in self.__pointed_tables_of_field_cache:
            return self.__pointed_tables_of_field_cache[cache_key]

        pointing_tables = self._get_pointing_tables(pointed_table_name)
        pointing_tables_on_field = []
        for table in pointing_tables:
            for rel in table.properties.relationships:
                for join_pair in rel.joinPairs:
                    if join_pair.toAttribute == pointed_field_name:
                        pointing_tables_on_field.append(table)
        self.__pointed_tables_of_field_cache[cache_key] = pointing_tables_on_field
        return pointing_tables_on_field

    def get_pointing_relationships_on_field(
        self, pointed_table_name: str, pointed_field_name: str
    ) -> list[RelationShip]:
        pointing_tables_on_field: list[ModelItem] = self._get_pointing_tables_on_field(
            pointed_table_name, pointed_field_name
        )
        relationships = []
        for table in pointing_tables_on_field:
            for rel in table.properties.relationships:
                for join_pair in rel.joinPairs:
                    if join_pair.toAttribute == pointed_field_name:
                        relationships.append(rel)
        return relationships

    def get_pointing_fks_on_field(self, pointed_table_name: str, pointed_field_name: str) -> list[JoinPair]:
        pointing_tables_on_field: list[ModelItem] = self._get_pointing_tables_on_field(
            pointed_table_name, pointed_field_name
        )
        join_pairs = []
        for table in pointing_tables_on_field:
            for rel in table.properties.relationships:
                for join_pair in rel.joinPairs:
                    if join_pair.toAttribute == pointed_field_name:
                        join_pairs.append(join_pair)
        return join_pairs

    def get_field_type(self, table_name: str, field_name: str) -> str:
        table = self.tables_dict[table_name]
        for column in table.storageDescriptor.columns:
            if column.name == field_name:
                return column.originDataTypeName.typeName
        raise ValueError(f"Field:'{field_name}' was not found in table:'{table_name}'")

    def get_pointed_tables_by_field(self, pointing_table_name: str, pointing_field_name: str) -> Optional[ModelItem]:
        pointing_table = self.tables_dict[pointing_table_name]
        for rel in pointing_table.properties.relationships:
            if rel.fromEntity == pointing_table_name:
                for join_pair in rel.joinPairs:
                    if join_pair.fromAttribute == pointing_field_name:
                        return self.tables_dict[rel.toEntity]
        return None

    def parse_with_db_semantics(self, db_semantics: SemanticsModel) -> dict[DataSourceId, TargetTableSchemaExt]:
        mapping = {}
        for table_model in self.tables:
            columns = set()
            relationships = frozenset(self._parse_relationship(rs) for rs in table_model.properties.relationships)
            self._fail_on_duplicate_columns(table_model)
            for column in table_model.storageDescriptor.columns:
                is_fk = False
                for rel in relationships:
                    for fk in rel.foreign_keys:
                        if fk.from_attribute == column.name:
                            is_fk = True
                            break
                columns.add(
                    TargetTableColumnExt(
                        name=column.name,
                        description=column.originDataTypeName.properties.description
                        if column.originDataTypeName.properties
                        else "",
                        type=CommonParsing.parse_field_type(
                            column.originDataTypeName.typeName,
                            FieldParsingExtraProps(
                                precision=column.originDataTypeName.precision,
                                scale=column.originDataTypeName.scale,
                            ),
                        ),
                        is_primary_key=column.name in table_model.properties.primaryKeys,
                        is_nullable=column.originDataTypeName.isNullable,
                        expression=None,
                        is_fk=is_fk,
                    )
                )
            columns = frozenset(columns)
            if table_model.name in db_semantics.duration_tables_dict:
                is_duration_table = True
                duration_semantics = from_DurationTable(
                    db_semantics.duration_tables_dict[table_model.name],
                )
            else:
                is_duration_table = False
                duration_semantics = None
            mapping[table_model.name] = TargetTableSchemaExt(
                id=table_model.name,
                relations=relationships,
                columns=columns,
                db=self.table_db_name(table_model),
                is_ref_table=db_semantics.is_reference_table(table_model.name),
                is_duration_table=is_duration_table,
                duration_semantics=duration_semantics,
                description=table_model.properties.description,
            )

        return mapping

    def _fail_on_duplicate_columns(self, table_model):
        """
        Raises ValueError if there are duplicate columns in the table
        this can create havok later on
        """
        duplicate_column = self.find_duplicate_value([c.name for c in table_model.storageDescriptor.columns])
        if duplicate_column:
            raise ValueError(
                f"Duplicate column '{duplicate_column}' was found in table '{table_model.name}'. It might due do ambiguity in SQL join statements"
            )

    def table_db_name(self, table: ModelItem) -> str:
        return table.namespace.databaseName

    def _parse_relationship(self, relationship: RelationShip) -> TableRelation:
        return TableRelation(
            foreign_keys=tuple(
                ForeignKey(from_attribute=jp.fromAttribute, to_attribute=jp.toAttribute)
                for jp in relationship.joinPairs
            ),
            from_entity=relationship.fromEntity,
            to_entity=relationship.toEntity,
        )

    def find_duplicate_value(self, lst: list[Any]) -> Optional[Any]:
        seen = set()
        for item in lst:
            if item in seen:
                return item
            seen.add(item)
        return None
