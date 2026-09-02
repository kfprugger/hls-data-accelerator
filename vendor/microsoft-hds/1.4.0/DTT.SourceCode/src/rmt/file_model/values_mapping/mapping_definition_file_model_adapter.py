from typing import Dict, List

from rmt.core.core_exceptions import ReferenceTableNotExistInRMTSpecError
from rmt.core.values_mapping.mapping_definition import MappingDefinition
from rmt.core.values_mapping.mapping_query_definition import MappingQueryDefinition, SourceMappingFile
from rmt.core.values_mapping.mapping_values_definition import MappingValuesDefinition, TargetMapping
from rmt.core.values_mapping.reference_table import ReferenceTable
from rmt.file_model.mapping_file_model import JSonItem, MappingFileModel, Table


class MappingDefinitionFileModelAdapter:

    def __init__(self, reference_tables: Dict[str, ReferenceTable]):
        self.reference_tables = reference_tables

    def to_core_model(self, file_name: str, file_content: str) -> MappingDefinition:

        if file_name not in self.reference_tables:
            raise ReferenceTableNotExistInRMTSpecError(file_name)
        try:
            file_model = MappingFileModel.from_str(file_content)
            if file_model.values:
                mapping_definition = MappingValuesDefinition(
                    file_name, self.reference_tables[file_name].key_field, MappingDefinitionFileModelAdapter.json_items_to_target_mapping(file_model.values)
                )
            elif file_model.query:
                mapping_definition = MappingQueryDefinition(
                    file_name,
                    self.reference_tables[file_name].key_field,
                    file_model.query.sql,
                    MappingDefinitionFileModelAdapter.tables_to_source_mapping_files(file_model.query.tables),
                )
            return mapping_definition
        except Exception as e:
            raise Exception(f"Error parsing mapping definition file '{file_name}'") from e

    @staticmethod
    def json_items_to_target_mapping(json_items: List[JSonItem]) -> List[TargetMapping]:
        return list(map(MappingDefinitionFileModelAdapter.json_item_to_target_mapping, json_items))

    @staticmethod
    def json_item_to_target_mapping(json_item: JSonItem) -> TargetMapping:
        return TargetMapping(json_item.targetKey, map(str, json_item.sourceKeys))

    @staticmethod
    def tables_to_source_mapping_files(tables: List[Table]) -> List[SourceMappingFile]:
        return list(map(MappingDefinitionFileModelAdapter.table_to_source_mapping_fie, tables))

    @staticmethod
    def table_to_source_mapping_fie(table: Table) -> SourceMappingFile:
        return SourceMappingFile(table.path, table.name)
