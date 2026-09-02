from enum import Enum

from pydantic import BaseModel


class NoExtrasBaseModel(BaseModel, extra="forbid"):
    pass


class FieldTypeEnum(str, Enum):
    string = "string"
    long = "long"
    integer = "integer"
    boolean = "boolean"
    bigint = "bigint"
    decimal = "decimal"
    datetime = "datetime"
    date = "date"
    timestamp = "timestamp"
    double = "double"
    float = "float"
    binary = "binary"
