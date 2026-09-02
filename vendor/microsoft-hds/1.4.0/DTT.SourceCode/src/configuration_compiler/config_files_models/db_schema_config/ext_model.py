import json
from collections import defaultdict
from copy import deepcopy
from typing import Optional

from configuration_compiler.config_files_models.db_schema.ext_model import DBSchemaModel
from configuration_compiler.config_files_models.db_schema.model import (
    Column,
    FieldProperties,
    JoinPair,
    ModelItem,
    OriginDataTypeName,
    RelationShip,
)
from configuration_compiler.config_files_models.db_schema_config.model import (
    ConfigField,
    DBConfigExtra,
    ExcludedFields,
    PrimaryKey,
    RawDBConfigModel,
)
from configuration_compiler.config_files_models.semantics.ext_model import SemanticsModel


class DBConfigModel(RawDBConfigModel):
    @classmethod
    def from_str(cls, db_schema_config: str) -> "DBConfigModel":
        try:
            db_config_model = cls(**json.loads(db_schema_config))
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse DB schema config: {e}") from e
        db_config_model.verify_extra_config()
        db_config_model.verify_fields_are_present_in_config()
        return db_config_model

    @staticmethod
    def _filter_required_tables(db_schema: DBSchemaModel, required_tables: dict[str, ExcludedFields]) -> DBSchemaModel:
        if not required_tables:
            return db_schema
        db_schema.tables = [t for t in db_schema.tables if t.name in required_tables]
        return db_schema

    @staticmethod
    def _remove_fields(db_schema: DBSchemaModel, required_tables: dict[str, ExcludedFields]) -> None:
        if not required_tables:
            return
        excluded_columns: Optional[ExcludedFields] = None

        def should_keep(column: Column):
            return column.name not in excluded_columns.exclude

        for table_model in db_schema.tables:
            excluded_columns = required_tables.get(table_model.name)
            if not excluded_columns:
                continue
            existing_columns: list[Column] = table_model.storageDescriptor.columns
            table_model.storageDescriptor.columns = list(filter(should_keep, existing_columns))

    @staticmethod
    def _add_fields(
        db_schema: DBSchemaModel,
        fields_to_add: list[ConfigField],
        configuration: DBConfigExtra,
        ref_tables: list[str],
    ) -> None:
        if not fields_to_add:
            return

        fields_grouped_by_table = defaultdict(list)
        for field in fields_to_add:
            if not field.enabled:
                continue
            config_field: ConfigField = deepcopy(field)
            config_field.tables = []
            relevant_tables = DBConfigModel._parse_required_tables_for_added_fields(
                configuration, db_schema, field, ref_tables
            )
            for table_name in relevant_tables:
                fields_grouped_by_table[table_name].append(config_field)
        fields_grouped_by_table = dict(fields_grouped_by_table)

        for table_model in db_schema.tables:
            existing_columns: list = table_model.storageDescriptor.columns
            for config_field in fields_grouped_by_table.get(table_model.name, []):
                new_column = Column(
                    name=config_field.name,
                    originDataTypeName=OriginDataTypeName(
                        typeName=config_field.type,
                        isNullable=True,
                        properties=FieldProperties(
                            minValue=None,
                            maxValue=None,
                            description=config_field.description,
                            dateFormat=None,
                            timestampFormat=None,
                        ),
                        length=None,
                        scale=None,
                        precision=None,
                    ),
                )
                datatype_config: OriginDataTypeName = new_column.originDataTypeName
                if config_field.length is not None:
                    datatype_config.length = config_field.length
                if config_field.scale is not None:
                    datatype_config.scale = config_field.scale
                if config_field.precision is not None:
                    datatype_config.precision = config_field.precision
                existing_columns.append(new_column)

    @staticmethod
    def _parse_required_tables_for_added_fields(
        configuration: DBConfigExtra, db_schema: DBSchemaModel, field: ConfigField, ref_tables: list[str]
    ) -> list[str]:
        field_tables = field.tables
        if field_tables == ["*"]:
            if field.name not in (
                configuration.sourceTableField,
                configuration.modifiedOnTargetField,
            ):
                raise ValueError(
                    f"Table name ('*') in the dbSchemaConfig file is only supported for config field names, e.g., ModifiedDate "
                    f"{(configuration.sourceTableField, configuration.modifiedOnTargetField)}"
                )
            # reference tables are not not altered with '*'
            all_tables_names = [t.name for t in db_schema.tables if t.name not in ref_tables]
            relevant_tables = all_tables_names
        else:
            if "*" in field_tables:
                raise ValueError(
                    f"Invalid table name ('*') in dbSchemaConfig file for config field '{field.name}': in position: {field_tables.index('*')}"
                )
            relevant_tables = field_tables
        return relevant_tables

    @staticmethod
    def _remove_redundant_relations(db_schema: DBSchemaModel, required_tables: Optional[dict]) -> DBSchemaModel:
        if not required_tables:
            return db_schema
        for table_model in db_schema.tables:
            filtered_relationships = []
            for r in table_model.properties.relationships:
                to_entity = r.toEntity
                if to_entity in required_tables:
                    filtered_relationships.append(r)
            table_model.properties.relationships = filtered_relationships
        return db_schema

    def verify_fields_are_present_in_config(self):
        if not self.fields:
            return
        if not self.configuration:
            return

        fields_names = [field.name for field in self.fields if field.enabled]
        for field in [
            self.configuration.modifiedOnTargetField,
            self.configuration.sourceTableField,
        ]:
            if field is not None:
                if field not in fields_names:
                    raise ValueError(f"Field '{field}' is not present in the dbSchemaConfig file")

    @staticmethod
    def _update_primary_keys(db_schema: DBSchemaModel, primary_keys: list[PrimaryKey]) -> None:
        for primary_key in primary_keys:
            try:
                table_model: ModelItem = db_schema.tables_dict[primary_key.table]
            except KeyError as ke:
                raise ValueError(f"Table '{primary_key.table}' was not found in the target schema") from ke
            old_pks = table_model.properties.primaryKeys[:]  # copy
            new_pks = table_model.properties.primaryKeys[:]  # copy
            existing_fields = [column.name for column in table_model.storageDescriptor.columns]
            for key_to_remove in primary_key.config.remove:
                if key_to_remove not in old_pks:
                    raise ValueError(
                        f"PK field '{key_to_remove}' was not found in the target table '{primary_key.table}'[0]"
                    )
                new_pks.remove(key_to_remove)
            for key_to_add in primary_key.config.add:
                if key_to_add in old_pks:
                    raise ValueError(
                        f"PK field '{key_to_add}' is already present in the PK fields collection of the target table '{primary_key.table}'[1]"
                    )
                if key_to_add not in existing_fields:
                    raise ValueError(
                        f"PK field '{key_to_add}' was not found in the PK fields collection of the target table '{primary_key.table}'[2]"
                    )
                new_pks.append(key_to_add)
            for old_key, new_key in primary_key.config.replace.items():
                if old_key not in existing_fields:
                    raise ValueError(
                        f"PK field '{old_key}' was not found in the PK fields collection of the target table '{primary_key.table}'[3]"
                    )
                if old_key not in old_pks:
                    raise ValueError(
                        f"PK field '{old_key}' was not found in the PK fields collection of the target table '{primary_key.table}'[4]"
                    )
                if new_key not in existing_fields:
                    raise ValueError(
                        f"PK field '{new_key}' was not found in the PK fields collection of the target table '{primary_key.table}'[5]"
                    )
                new_pks.remove(old_key)
                new_pks.append(new_key)
            table_model.properties.primaryKeys = new_pks
            DBConfigModel._update_primary_keys_in_relationships(db_schema, primary_key, table_model)

    @staticmethod
    def _update_primary_keys_in_relationships(
        db_schema: DBSchemaModel, primary_key: PrimaryKey, table_model: ModelItem
    ):
        # update all fks that reference this table
        for old_key, new_key in primary_key.config.replace.items():
            pointing_join_pairs: list[JoinPair] = db_schema.get_pointing_fks_on_field(table_model.name, old_key)
            for join_pair in pointing_join_pairs:
                join_pair.toAttribute = new_key
        for key_to_remove in primary_key.config.remove:
            pointing_relationships: list[RelationShip] = db_schema.get_pointing_relationships_on_field(
                table_model.name, key_to_remove
            )
            for rel in pointing_relationships:
                rel.joinPairs = list(filter(lambda jp: jp.toAttribute != key_to_remove, rel.joinPairs))

    def adapt_schema(self, db_schema: DBSchemaModel, db_semantics: SemanticsModel | None) -> DBSchemaModel:
        db_schema = DBConfigModel._filter_required_tables(db_schema, self.tables)
        db_schema = DBConfigModel._remove_redundant_relations(db_schema, self.tables)
        DBConfigModel._remove_fields(db_schema, self.tables)
        ref_tables = [t.table for t in db_semantics.referenceTables] if db_semantics else []
        DBConfigModel._add_fields(db_schema, self.fields, self.configuration, ref_tables)
        DBConfigModel._update_primary_keys(db_schema, self.primaryKeys)
        return db_schema

    def verify_extra_config(self):
        if bool(self.configuration.modifiedOnTargetField) ^ bool(self.configuration.sourceTableField):
            raise ValueError(
                "Both modifiedOnTargetField and sourceTableField must be specified, or neither of them. In the DB target schema config file"
            )
