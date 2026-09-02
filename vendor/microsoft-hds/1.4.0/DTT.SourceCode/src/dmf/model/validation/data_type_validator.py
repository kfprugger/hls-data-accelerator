from pyspark.sql.types import DataType
from common.model.data_type_serializer import DataTypeSerializer


class DataTypeValidator:
    def validate(value) -> DataType:
        if isinstance(value, str):
            return DataTypeSerializer.deserialize(value)
        elif isinstance(value, DataType):
            return value
        else:
            raise TypeError(f"Error validating DataType. type: {type(value)}")
