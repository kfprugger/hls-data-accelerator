from enum import Enum


class DataSourceTypeEnum(str, Enum):
    """
    TABLE value means that access to datasource will be done through hive metastore
    QUERY value - not supported
    STORAGE value means that access to datasource will be done directly storage
    """

    TABLE = "TABLE"
    QUERY = "QUERY"
    STORAGE = "STORAGE"
