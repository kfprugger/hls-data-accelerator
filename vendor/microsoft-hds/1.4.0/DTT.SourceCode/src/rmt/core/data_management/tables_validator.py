from typing import List, Set

from rmt.core.core_exceptions import MappingTargetKeyNotExistsInTableError
from rmt.core.data_management.primitive_types import TableName
from rmt.core.data_management.repository import Repository
from rmt.core.data_management.table_data import TableData
from rmt.core.data_management.table_data_appender import TableDataAppender
from rmt.core.data_management.table_mapping import TableMapping
from rmt.core.data_management.table_mapping_appender import TableMappingAppender


class TablesValidator:
    """
    this class is responsible for validating the data and mapping of the tables
    it uses the repository to get the data and mapping of the tables
    it first validate the data of the table by adding all TableData of the table from different contributors
    then it validate the mapping of the table by adding all TableMapping of the table from different contributors
    then it validate the mapping with the data of the table by checking that each target key of the mapping exist in the data
    """

    @property
    def validation_errors(self) -> List[ValueError]:
        return self._errors

    def __init__(self, repository: Repository):
        self._repository = repository
        self._invalid_table_names: Set[TableName] = set()
        self._errors: List[ValueError] = []

    def _add_invalid_table(self, table_name: TableName):

        if table_name not in self._invalid_table_names:
            self._invalid_table_names.add(table_name)

    def _get_table_data(self, table_name: str) -> TableData:

        table_data_appender = TableDataAppender(table_name)
        table_data_list = self._repository.get_table_data_list_by_table(table_name)
        for table_data in table_data_list:
            table_data_appender.append(table_data)
        if table_data_appender.errors:
            self._add_invalid_table(table_name)
            for error in table_data_appender.errors:
                self._errors.append(error)
        return table_data_appender.table_data

    def _get_table_mapping(self, table_name: str) -> TableMapping:

        table_mapping_appender = TableMappingAppender(table_name)
        table_mapping_list = self._repository.get_table_mapping_list_by_table(table_name)
        for table_mapping in table_mapping_list:
            table_mapping_appender.append(table_mapping)
        if table_mapping_appender.errors:
            self._add_invalid_table(table_name)
            for error in table_mapping_appender.errors:
                self._errors.append(error)
        return table_mapping_appender.table_mapping

    def _validate_mapping_with_data(self, table_name: str, table_data: TableData, table_mapping: TableMapping):
        for target_key, source_values in table_mapping.target_to_source_mapping.items():
            if not table_data.key_exist_in_data(target_key):
                self._add_invalid_table(table_name)
                self._errors.append((MappingTargetKeyNotExistsInTableError(table_name, source_values, target_key)))

    def _validate_table(self, table_name: str):

        try:
            # Validate table data for table by it to one table data"
            aggregated_table_data = self._get_table_data(table_name)
            # Validate table data for table by it to one table mapping"
            aggregated_table_mapping = self._get_table_mapping(table_name)
            # Validate table mapping with table data."
            if aggregated_table_data is not None and aggregated_table_mapping is not None:
                self._validate_mapping_with_data(table_name, aggregated_table_data, aggregated_table_mapping)
        except ValueError as error:
            self._add_invalid_table(table_name)
            self._errors.append(error)

    def validate_tables(self, table_names: Set[str]) -> bool:
        self._invalid_table_names = set()
        self._errors = []
        for table_name in table_names:
            self._validate_table(table_name)
        return len(self._invalid_table_names) == 0
