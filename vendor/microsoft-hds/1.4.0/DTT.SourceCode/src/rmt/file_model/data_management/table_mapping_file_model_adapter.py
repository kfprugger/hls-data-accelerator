from typing import Dict, List, Set

from rmt.core.data_management.table_mapping import SourceValue, TableMapping, TargetKey
from rmt.core.values_mapping.mapping_query_definition import SourceMappingFile
from rmt.core.values_mapping.reference_table import ReferenceTable
from rmt.file_model.mapping_file_model import JSonItem, MappingFileModel, SQLItem, Table


class TableMappingFileModelAdapter:

    @staticmethod
    def from_core_model(table_mapping: TableMapping) -> MappingFileModel:
        json_values = TableMappingFileModelAdapter.mappings_values_to_json_items(table_mapping.target_to_source_mapping)
        return MappingFileModel(values=json_values)

    @staticmethod
    def to_core_model(file_model: MappingFileModel, reference_table: ReferenceTable) -> TableMapping:

        try:
            if file_model.values is not None:
                mapping_definition = TableMapping(reference_table.table_name)
                TableMappingFileModelAdapter.add_json_items(mapping_definition, file_model.values)
                return mapping_definition
        except Exception as e:
            raise ValueError(f"Error converting to table mapping. file '{reference_table.table_name}'") from e

    @staticmethod
    def add_json_items(table_mapping: TableMapping, json_items: List[JSonItem]):
        for json_item in json_items:
            table_mapping.add_target_mapping(json_item.targetKey, list(map(str, json_item.sourceKeys)))

    @staticmethod
    def tables_to_source_mapping_files(tables: List[Table]) -> List[SourceMappingFile]:
        return list(map(TableMappingFileModelAdapter.table_to_source_mapping_fie, tables))

    @staticmethod
    def table_to_source_mapping_fie(table: Table) -> SourceMappingFile:
        return SourceMappingFile(table.path, table.name)

    @staticmethod
    def mappings_values_to_json_items(mapping_values: Dict[TargetKey, Set[SourceValue]]) -> List[JSonItem]:
        result: List[JSonItem] = []
        for mapping_value in mapping_values:
            result.append(JSonItem(targetKey=mapping_value, sourceKeys=list(mapping_values[mapping_value])))
        return result

    @staticmethod
    def source_mapping_files_to_tables(source_mapping_files: List[SourceMappingFile]) -> List[Table]:
        return list(map(TableMappingFileModelAdapter.source_mapping_file_to_table, source_mapping_files))

    @staticmethod
    def source_mapping_file_to_table(source_mapping_file: SourceMappingFile) -> Table:
        return Table(name=source_mapping_file.file_name, path=source_mapping_file.file_path)

    @staticmethod
    def query_and_mapping_files_to_sql_item(query: str, source_mapping_files: List[SourceMappingFile]) -> SQLItem:
        return SQLItem(tables=TableMappingFileModelAdapter.source_mapping_files_to_tables(source_mapping_files), sql=query)
