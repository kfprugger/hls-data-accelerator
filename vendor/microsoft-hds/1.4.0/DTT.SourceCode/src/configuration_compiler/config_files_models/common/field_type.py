from dataclasses import dataclass
from typing import Optional

from configuration_compiler.config_files_models.models_base import FieldTypeEnum
from pyspark.sql.types import (
    BinaryType,
    BooleanType,
    DataType,
    DateType,
    DecimalType,
    DoubleType,
    FloatType,
    IntegerType,
    LongType,
    StringType,
    TimestampType,
)

_FIELD_TYPES = {
    FieldTypeEnum.integer: IntegerType,
    FieldTypeEnum.bigint: LongType,
    FieldTypeEnum.string: StringType,
    FieldTypeEnum.decimal: DecimalType,
    FieldTypeEnum.double: DoubleType,
    FieldTypeEnum.float: FloatType,
    FieldTypeEnum.timestamp: TimestampType,
    FieldTypeEnum.boolean: BooleanType,
    FieldTypeEnum.datetime: TimestampType,
    FieldTypeEnum.date: DateType,
    FieldTypeEnum.long: LongType,
    FieldTypeEnum.binary: BinaryType,
}


@dataclass
class FieldParsingExtraProps:
    precision: Optional[int]
    scale: Optional[int]


class CommonParsing:
    @staticmethod
    def parse_field_type(field_type: FieldTypeEnum, extra_props: Optional[FieldParsingExtraProps] = None) -> DataType:
        try:
            if field_type == FieldTypeEnum.decimal:
                return CommonParsing._parse_decimal_field(extra_props=extra_props)
            return _FIELD_TYPES[field_type]()
        except KeyError as e:
            raise Exception(f"Unknown target field type defined in the adapter file: '{field_type}'.") from e

    @staticmethod
    def _parse_decimal_field(
        extra_props: Optional[FieldParsingExtraProps] = None,
    ) -> DataType:
        if extra_props is not None and extra_props.precision is not None and extra_props.scale is not None:
            return DecimalType(precision=extra_props.precision, scale=extra_props.scale)
        return DecimalType()
