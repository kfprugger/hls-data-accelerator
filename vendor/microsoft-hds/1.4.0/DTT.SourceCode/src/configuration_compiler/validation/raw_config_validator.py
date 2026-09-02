
from collections import defaultdict
from typing import List
from configuration_compiler.config_files_models.adapter.ext_model import AdapterModel
from configuration_compiler.spec_models.target_table_schema import TargetTableSchemaExt
from configuration_compiler.validation.validation_exception import ValidationException
from common.model.types import DataSourceId


class MissingPrimaryKeysTransformationsForAnchor(ValidationException):
    pass


class MissingIntegrtionKeyDefinition(ValidationException):
    pass


class RawConfigValidator:
    """
    This class is responsible for validating the raw configuration.
    It is used to validate the following:
    - All the anchors have primary keys transformations
    It is desinged to be called after the raw configuration is ready to be compiled to the DMF model
    and for UI validation/auto-complition purposes while users are in the process of composing the configuration.
    """
    def __init__(
        self,
        adapter: AdapterModel,
        target_tables_schemas: dict[DataSourceId, TargetTableSchemaExt],
    ):
        self.adapter = adapter
        self.target_tables_schemas = target_tables_schemas

    def validate(self):
        self._validate_anchor_tables_integration_keys()

    def _validate_anchor_tables_integration_keys(self):

        anchor_tables_requiring_replacement_field: set[str] = set()
        adapter_source_to_anchor_tables_dict: dict[str, List[str]] = defaultdict(list)
        source_to_replacement_keys_dict: dict[str, set[str]] = defaultdict(set)
        for source_table in self.adapter.source_tables:
            anchor_table_names = [anchor_table.tableName for anchor_table in source_table.targetAnchorTables]
            source_table_name = source_table.tableName
            adapter_source_to_anchor_tables_dict[source_table_name] = anchor_table_names
            source_to_replacement_keys_dict[source_table_name] = set()

            # Create a dictionary mapping field names to source_field objects
            field_name_to_source_field = {source_field.fieldName: source_field for source_field in source_table.sourceFields}

            for field_replacement_key in source_table.pkInternalExternalPairs:
                source_field = field_name_to_source_field.get(field_replacement_key.internalField)
                if source_field is not None:
                    # map target tables
                    for target_field in source_field.targetFields.fields:
                        if target_field.tableName in anchor_table_names:
                            anchor_tables_requiring_replacement_field.add(target_field.tableName)
                            source_to_replacement_keys_dict[source_table_name].add(target_field.tableName)

        for source_table_name in source_to_replacement_keys_dict.keys():
            source_anchor_tables = adapter_source_to_anchor_tables_dict[source_table_name]
            for anchor_table in source_anchor_tables:
                source_anchor_tables_with_replacement_keys = source_to_replacement_keys_dict[source_table_name]
                if anchor_table in anchor_tables_requiring_replacement_field and not (anchor_table in source_anchor_tables_with_replacement_keys):
                    raise MissingIntegrtionKeyDefinition(f"Anchor table '{anchor_table}' for source table '{source_table_name}' must have a replacement field defined")
