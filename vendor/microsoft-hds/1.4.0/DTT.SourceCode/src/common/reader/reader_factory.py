from common.model.data_access_definition import DataAccessDefinition
from common.model.data_source_type_enum import DataSourceTypeEnum
from common.reader.query_reader import QueryReader
from common.reader.storage_reader import StorageReader
from common.reader.table_reader import TableReader


def table_reader(data_access_definition: DataAccessDefinition) -> TableReader:
    return TableReader(
        db=data_access_definition.data_source_owner_id,
        table=data_access_definition.data_source_id,
    )


def query_reader(data_access_definition: DataAccessDefinition) -> QueryReader:
    return QueryReader(
        db=data_access_definition.data_source_owner_id,
        query=data_access_definition.data_source_id,
    )


def storage_reader(data_access_definition: DataAccessDefinition) -> StorageReader:
    return StorageReader(
        location=data_access_definition.data_source_owner_id,
        data_format=data_access_definition.data_format
    )


def default(data_access_definition: DataAccessDefinition):
    raise ValueError(
        f"Adapter source table's data type '{data_access_definition.data_source_type}' is not supported"
    )


class ReaderFactory:
    @staticmethod
    def get_instance(data_access_definition: DataAccessDefinition):
        match data_access_definition.data_source_type:
            case DataSourceTypeEnum.TABLE:
                return table_reader(data_access_definition)
            case DataSourceTypeEnum.QUERY:
                return query_reader(data_access_definition)
            case DataSourceTypeEnum.STORAGE:
                return storage_reader(data_access_definition)
            case _:
                return default(data_access_definition)
