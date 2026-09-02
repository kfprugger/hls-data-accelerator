from pyspark.sql.types import BinaryType, BooleanType, ByteType, DateType, DecimalType, DoubleType, FloatType, IntegerType, LongType, NullType, ShortType, StringType, TimestampType

data_types = [IntegerType(), StringType(), FloatType(), DoubleType(), LongType(), ShortType(), ByteType(), BooleanType(), DateType(), TimestampType(), BinaryType(), NullType()]
simple_string_to_data_type = {t.simpleString(): t for t in data_types}
data_type_to_simple_string = {t: t.simpleString() for t in data_types}
decimal_simple_string_prefix = DecimalType().simpleString().split("(")[0]


class DataTypeSerializer:

    @staticmethod
    def serialize(value):
        if (value in data_type_to_simple_string):
            return data_type_to_simple_string[value]
        elif isinstance(value, DecimalType):
            return value.simpleString()
        else:
            raise ValueError(f"Cannot serialize Data type: {value}")

    @staticmethod
    def deserialize(value):
        if (value in simple_string_to_data_type):
            return simple_string_to_data_type[value]
        elif value.split("(")[0] == decimal_simple_string_prefix:
            precision, scale = value.split("(")[1].split(")")[0].split(",")
            return DecimalType(precision=int(precision), scale=int(scale))
        else:
            raise ValueError(f"Cannot deserialize Data type: {value}")
