from decimal import Context, Decimal, InvalidOperation

from pyspark.sql.types import BooleanType  # Represents boolean values (true or false).
from pyspark.sql.types import ByteType  # Represents 1-byte signed integer numbers. The range is from -128 to 127.
from pyspark.sql.types import DecimalType  # Represents arbitrary-precision signed decimal numbers
from pyspark.sql.types import DoubleType  # Represents 8-byte double-precision floating point numbers.
from pyspark.sql.types import FloatType  # Represents 4-byte single-precision floating point numbers.
from pyspark.sql.types import IntegerType  # Represents 4-byte signed integer numbers. The range is from -2,147,483,648 to 2,147,483,647.
from pyspark.sql.types import LongType  # Represents 8-byte signed integer numbers. The range is from -9,223,372,036,854,775,808 to 9,223,372,036,854,775,807.
from pyspark.sql.types import ShortType  # Represents 2-byte signed integer numbers. The range is from -32,768 to 32,767.
from pyspark.sql.types import DataType, StringType


class JSONToSparkTypeConvertor:
    def convert_json_to_spark_compatible_type(self, json_val: int | str | float | bool | None, spark_type: DataType) -> int | str | float | bool | None:
        if json_val is None:
            return None
        if isinstance(json_val, bool) and spark_type == BooleanType():
            return json_val
        if isinstance(json_val, str):
            return self._try_convert_string_to_spark_data_type(json_val, spark_type)
        if isinstance(json_val, int) and not isinstance(json_val, bool):
            return self._try_convert_int_to_spark_data_type(json_val, spark_type)
        if isinstance(json_val, float):
            return self._try_convert_float_to_spark_data_type(json_val, spark_type)
        raise TypeError(f"Unexpected JSON type {type(json_val)} for {json_val}")

    def _try_convert_string_to_spark_data_type(self, json_val: str, spark_type: DataType) -> int | str | float:
        if spark_type == StringType():
            return json_val
        if spark_type in [IntegerType(), ByteType(), ShortType(), LongType()]:
            try:
                return int(json_val)
            except ValueError as ve:
                raise TypeError(f"Cannot convert json value {json_val} of type str to spark type {spark_type}") from ve
        if spark_type in [FloatType(), DoubleType()]:
            try:
                return float(json_val)
            except ValueError as ve:
                raise TypeError(f"Cannot convert json value {json_val} of type str to spark type {spark_type}") from ve
        if isinstance(spark_type, DecimalType):
            try:
                return Decimal(json_val, Context(prec=spark_type.precision))
            except InvalidOperation as ve:
                raise TypeError(f"Cannot convert json value {json_val} of type str to spark type {spark_type}") from ve
        else:
            raise TypeError(f"Cannot convert json value {json_val} of type str to spark type {spark_type}")

    def _try_convert_int_to_spark_data_type(self, json_val: int, spark_type: DataType) -> int | str | float:
        if spark_type in [IntegerType(), ByteType(), ShortType(), LongType()]:
            return json_val
        if spark_type in [FloatType(), DoubleType()]:
            return float(json_val)
        if spark_type == StringType():
            return str(json_val)
        if isinstance(spark_type, DecimalType):
            return Decimal(str(json_val), Context(prec=spark_type.precision))
        raise TypeError(f"Cannot convert json value {json_val} of type int to spark type {spark_type}")

    def _try_convert_float_to_spark_data_type(self, json_val: float, spark_type: DataType) -> int | str | float:
        if spark_type in [FloatType(), DoubleType()]:
            return json_val
        if spark_type == StringType():
            return str(json_val)
        if isinstance(spark_type, DecimalType):
            return Decimal(str(json_val), Context(prec=spark_type.precision))
        raise TypeError(f"Cannot convert json value {json_val} of type float to spark type {spark_type}")
