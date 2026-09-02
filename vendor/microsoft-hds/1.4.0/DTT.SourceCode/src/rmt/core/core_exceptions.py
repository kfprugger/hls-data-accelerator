from typing import List, Set

from rmt.core.data_management.primitive_types import SourceValue, TargetKey


class UpdateError(ValueError):
    pass


class AuthoringFilesGenerationError(ValueError):
    pass


class UpdateValueError(UpdateError):
    def __init__(self, table_name: str, message: str):
        super().__init__(f"{table_name}\t{message}")


class EntryKeyAlreadyExistsError(UpdateValueError):

    def __init__(self, table_name: str, key: int):
        super().__init__(table_name, f"Reference key '{key}' already defined in this table.")


class EntryNameAlreadyExistsError(UpdateValueError):
    def __init__(self, table_name: str, name: str):
        super().__init__(table_name, f"Reference name '{name}' already defined in this table.")


class EntryNameIsEmpty(UpdateValueError):
    def __init__(self, table_name: str):
        super().__init__(table_name, "Reference name is empty.")


class MappingSourceValueAlreadyExistsError(UpdateValueError):
    def __init__(self, table_name: str, source_value: str):
        super().__init__(table_name, f"Source value '{source_value} already mapped.")


class KeyOutOfRangeError(UpdateValueError):
    def __init__(self, table_name: str, contributor: str, value: int):
        super().__init__(table_name, f"Key '{value}' is out of contributor '{contributor}' keys range.")


class MappingTargetKeyNotExistsInTableError(UpdateValueError):

    def __init__(self, table_name: str, source_values: Set[SourceValue], target_key: TargetKey):
        super().__init__(
            table_name,
            f"Invalid mapping of source value/s {source_values} to target ID '{target_key}', target ID not exist in table keys.",
        )


class ReferenceTableNotExistInRMTSpecError(UpdateValueError):
    def __init__(self, table_name: str):
        super().__init__(table_name, "is not defined as reference table in semantics file.")


class TargetIdIsNotNumericError(UpdateValueError):
    def __init__(self, table_name: str, source_value: str, target_key: str):
        super().__init__(table_name, f"Invalid mapping of source value {source_value} to target ID '{target_key}', target ID should be a number.")


class SourceValueIsEmptyError(UpdateValueError):
    def __init__(self, table_name: str, source_value: str):
        super().__init__(table_name, f"Invalid source value: '{source_value}', should not be empty.")


class IdValueIsNotNumericError(UpdateValueError):
    def __init__(self, table_name: str, id: str):
        super().__init__(table_name, f"Invalid id value: '{id}', should be a number.")


class NonExistingContributorUpdateError(UpdateValueError):
    def __init__(self, table_name: str, contributor_name: str):
        super().__init__(table_name, f"Contributor '{contributor_name}' is not a valid contributor name.")


class NoSourceDataError(AuthoringFilesGenerationError):

    def __init__(self, source_id: str, data_source_id: str):
        super().__init__(
            f"Cannot read source distinct values, source processor has no data to process."
            f"Please refer to the logs for more information."
            f"Source ID: {source_id}"
            f"Data source ID: {data_source_id}"
        )


class InputValueError(ValueError):
    pass


class AddContributorTableDataError(InputValueError):
    def __init__(self, table_name: str, contributor_name: str):
        super().__init__(f"Trying to add data of table '{table_name}' which already exists for contributor '{contributor_name}'.")


class AddContributorTableMappingError(InputValueError):
    def __init__(self, table_name: str, contributor_name: str):
        super().__init__(f"Trying to add mapping of table '{table_name}' which already exists for contributor '{contributor_name}'.")


class TableDataAddError(InputValueError):
    def __init__(self, table_name1: str, table_name2: str):
        super().__init__(f"Trying to add data of table '{table_name1}' to data of table '{table_name2}'.")


class TableMappingAddError(InputValueError):
    def __init__(self, table_name1: str, table_name2: str):
        super().__init__(f"Trying to add mapping of table '{table_name1}' to mapping of table '{table_name2}'.")


class NonExistingContributorInputError(InputValueError):
    def __init__(self, contributor_name: str):
        super().__init__(f"Calling method with contributor '{contributor_name}' which does not exist in the repository.")


class NonExistingPredefinedNameError(ValueError):
    def __init__(self, name: str):
        super().__init__(f"Trying to call get predfined name '{name}' which does not exist in predefined names.")


class AuthoringFileError(Exception):
    def __init__(self, file_path, authroing_type: str, error: str):
        super().__init__(f"Error reading authoring {authroing_type} file from path {file_path}: {error}")


class AuthoringMappingColumnMissingError(AuthoringFileError):
    def __init__(self, file_path, column_names: List[str]):
        super().__init__(file_path=file_path, authroing_type="mapping", error=f"One or more missing column: {column_names}")


class AuthoringDataColumnMissingError(AuthoringFileError):
    def __init__(self, file_path, column_names: List[str]):
        super().__init__(file_path=file_path, authroing_type="data", error=f"One or more missing column: {column_names}")


class AuthoringMappingFileNotExistError(AuthoringFileError):
    def __init__(self, file_path: str):
        super().__init__(file_path=file_path, authroing_type="mapping", error="File does not exist.")


class AuthoringDataFileNotExistError(AuthoringFileError):
    def __init__(self, file_path: str):
        super().__init__(file_path=file_path, authroing_type="data", error="File does not exist.")
