from pydantic import Field, field_serializer, validator
from pyspark.sql.types import (BinaryType, BooleanType, ByteType, DataType, DateType, DecimalType, DoubleType, FloatType, IntegerType, LongType, NullType, ShortType, StringType,
                               TimestampType)

from rmt.contract.configuration.common.immutable_model import ImmutableModel

integer_simple_string = IntegerType().simpleString()
string_simple_string = StringType().simpleString()
float_simple_string = FloatType().simpleString()
double_simple_string = DoubleType().simpleString()
long_simple_string = LongType().simpleString()
short_simple_string = ShortType().simpleString()
byte_simple_string = ByteType().simpleString()
boolean_simple_string = BooleanType().simpleString()
date_simple_string = DateType().simpleString()
timestamp_simple_string = TimestampType().simpleString()
binary_simple_string = BinaryType().simpleString()
null_simple_string = NullType().simpleString()
decimal_simple_string_prefix = DecimalType().simpleString().split("(")[0]

simple_string_to_data_type: dict[str, DataType] = {
    integer_simple_string: IntegerType(),
    string_simple_string: StringType(),
    float_simple_string: FloatType(),
    double_simple_string: DoubleType(),
    long_simple_string: LongType(),
    short_simple_string: ShortType(),
    byte_simple_string: ByteType(),
    boolean_simple_string: BooleanType(),
    date_simple_string: DateType(),
    timestamp_simple_string: TimestampType(),
    binary_simple_string: BinaryType(),
    null_simple_string: NullType(),
}

data_type_to_simple_string: dict[DataType, str] = {
    IntegerType(): integer_simple_string,
    StringType(): string_simple_string,
    FloatType(): float_simple_string,
    DoubleType(): double_simple_string,
    LongType(): long_simple_string,
    ShortType(): short_simple_string,
    ByteType(): byte_simple_string,
    BooleanType(): boolean_simple_string,
    DateType(): date_simple_string,
    TimestampType(): timestamp_simple_string,
    BinaryType(): binary_simple_string,
    NullType(): null_simple_string,
}


class DataTypeValidator:
    @staticmethod
    def validate(value) -> DataType:
        if isinstance(value, str):
            return DataTypeSerializer.deserialize(value)
        elif isinstance(value, DataType):
            return value
        else:
            raise TypeError(f"Error validating DataType. type: {type(value)}")


class DataTypeSerializer:
    @staticmethod
    def serialize(value):
        if value in data_type_to_simple_string:
            return data_type_to_simple_string[value]
        elif isinstance(value, DecimalType):
            return value.simpleString()
        else:
            raise ValueError(f"Cannot serialize Data type: {value}")

    @staticmethod
    def deserialize(value):
        if value in simple_string_to_data_type:
            return simple_string_to_data_type[value]
        elif value.split("(")[0] == decimal_simple_string_prefix:
            precision, scale = value.split("(")[1].split(")")[0].split(",")
            return DecimalType(precision=int(precision), scale=int(scale))
        else:
            raise ValueError(f"Cannot deserialize Data type: {value}")


class TableColumn(ImmutableModel):
    name: str = Field(...)
    type: DataType = Field(...)
    is_nullable: bool = Field(...)

    @validator("type", pre=True)
    @classmethod
    def validate_type(cls, value):
        return DataTypeValidator.validate(value)

    @field_serializer("type")
    def serialize_type(self, value):
        return DataTypeSerializer.serialize(value)

    def __str__(self):
        return f"Column({self.name}: {self.type.simpleString()})"


class ReferenceTable(ImmutableModel):
    table_name: str = Field(..., description="Reference table name, e.g., Gender")
    key_field: str = Field(..., description="The key field of a reference table")
    name_field: str = Field(..., description="The default 'name' field of a reference table")
    columns: list[TableColumn] = Field(...)

    def __str__(self):
        return f"ReferenceTable(table={self.table_name}, keyField={self.key_field}, nameField={self.name_field}, columns={self.columns})"

    def __repr__(self):
        return self.__str__()
