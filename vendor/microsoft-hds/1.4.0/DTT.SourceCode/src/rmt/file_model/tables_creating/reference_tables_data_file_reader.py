from collections import defaultdict
from typing import Dict, List, Set

import rmt.core.logger as logger
from rmt.core.tables_creating.model.internal import ReferenceTableData, ReferenceTableFieldMapping
from rmt.core.tables_creating.reference_tables_data_reader import ReferenceTablesDataReader
from rmt.file_model.data_file_model import DataFileModel, FieldMapping
from rmt.filesystem.file_system_client import FileSystemClient
from rmt.filesystem.files_reader import FilesReader


class ReferenceTablesDataFileReader(ReferenceTablesDataReader):

    def __init__(
        self,
        file_system_client: FileSystemClient,
        reference_tables_data_folders: List[str],
        reference_table_names: Set[str],
    ):
        self._file_system_client = file_system_client
        self._reference_table_data_folders = reference_tables_data_folders
        self._reference_table_names = reference_table_names

    def read(self) -> Dict[str, List[ReferenceTableData]]:
        logger.info("Reading reference tables data")
        if not self._reference_table_data_folders:
            logger.info("No reference tables data folders found")
            return {}
        files_contents = defaultdict(list)
        for folder in self._reference_table_data_folders:
            logger.info(f"Reading files from folder {folder}")
            file_contents_by_file_name = FilesReader.read_folder_content(self._file_system_client, folder)
            for name, content in file_contents_by_file_name.items():
                if name in self._reference_table_names:
                    logger.info(f"Reading data from file {name}")
                    files_contents[name].append(content)
        reference_tables_data: Dict[str, List[DataFileModel]] = defaultdict(list)
        for file_name, file_contents in files_contents.items():
            for file_content in file_contents:
                reference_tables_data[file_name].append(DataFileModel.model_validate_json(file_content))
        return dict(self._convert_to_internal_model(reference_tables_data))

    def _convert_to_internal_model(self, reference_tables_data: Dict[str, List[DataFileModel]]):
        return {k: self._to_internal_model_tables(tables_data) for k, tables_data in reference_tables_data.items()}

    def _to_internal_model_tables(self, tables_data: List[DataFileModel]) -> ReferenceTableData:
        return [self._to_internal_model_table(c) for c in tables_data]

    def _to_internal_model_table(self, table_data: DataFileModel) -> ReferenceTableData:
        return ReferenceTableData(
            adrmTableName=table_data.adrmTableName,
            fieldMapping=[self._to_internal_model_field_mapping(c) for c in table_data.fieldMapping],
            data=table_data.data,
        )

    def _to_internal_model_field_mapping(self, field_mapping: FieldMapping) -> ReferenceTableFieldMapping:
        return ReferenceTableFieldMapping(adrmFieldName=field_mapping.adrmFieldName, referenceFieldName=field_mapping.referenceFieldName)
