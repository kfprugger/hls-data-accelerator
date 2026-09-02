from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from pyspark.sql import DataFrame, Row, SparkSession
from pyspark.sql.types import StructField, StructType

import rmt.core.logger as logger
from rmt.core.tables_creating.json_spark_numeric_convertor import JSONToSparkTypeConvertor
from rmt.core.tables_creating.model.internal import ReferenceTable, ReferenceTableData, TableColumn


class UnExpectedNullValueError(Exception):
    pass


class CreateDataFrameError(Exception):
    pass


class ReferenceTablesWriter:
    def __init__(
        self,
        spark: SparkSession,
        reference_tables_data: dict[str, list[ReferenceTableData]],
        reference_tables: dict[str, ReferenceTable],
        target_path: str,
    ):
        self._spark = spark
        self._reference_tables_data = reference_tables_data
        self._reference_tables = reference_tables
        self._target_path = target_path
        self._type_convertor = JSONToSparkTypeConvertor()

    def overwrite(self):
        futures: list[Future] = []
        with ThreadPoolExecutor(thread_name_prefix="ref-table-writer") as executor:
            for table_name, tables_data in self._reference_tables_data.items():
                single_table_data_df = self._create_dataframe(tables_data, table_name, self._reference_tables[table_name].columns)
                f = executor.submit(self._write_table, single_table_data_df, table_name)
                futures.append(f)
        for f in futures:
            f.result()

    def _create_dataframe(self, tables_data: list[ReferenceTable], table_name: str, ref_table_columns: list[TableColumn]) -> DataFrame:
        schema = self._gen_ref_table_schema(ref_table_columns)
        data_rows = []
        for table_data in tables_data:
            field_mapping_dict = {m.adrmFieldName: m.referenceFieldName for m in table_data.fieldMapping}
            data_rows += [self._gen_data_row(row_dict, field_mapping_dict, schema, table_name, row_num + 1) for row_num, row_dict in enumerate(table_data.data)]
        try:
            return self._spark.createDataFrame(data_rows, schema)
        except Exception as e:
            logger.error(f"Error creating dataframe for table {table_name} failed")
            raise CreateDataFrameError(f"Error creating dataframe for table {table_name}") from e

    def _gen_ref_table_schema(self, ref_table_columns: list[TableColumn]):
        fields = [self._gen_ref_table_field(column) for column in ref_table_columns]
        return StructType(fields)

    def _gen_ref_table_field(self, column: TableColumn):
        return StructField(column.name, column.type, column.is_nullable)

    def _gen_data_row(
        self,
        row_dict: dict[str, Any],
        field_mapping_dict: dict[str, str],
        schema: StructType,
        table_name: str,
        row_num: int,
    ) -> Row:
        row_data = {}
        for column in schema:
            if column.name in field_mapping_dict:
                row_value_json = row_dict.get(field_mapping_dict[column.name])
                row_value = self._type_convertor.convert_json_to_spark_compatible_type(row_value_json, column.dataType)
            else:
                row_value = None
            if row_value is None and not column.nullable:
                raise UnExpectedNullValueError(f"Table: {table_name}, data row: {row_num}, Column {column.name} is not nullable")
            row_data[column.name] = row_value
        return Row(**row_data)

    def _write_table(self, df: DataFrame, table_name: str):
        target_table_path = f"{self._target_path}/{table_name}"
        logger.info(f"Writing table {table_name} to {target_table_path}. Delta format. Columns: {df.columns}")
        try:
            df.write.mode("overwrite").format("delta").save(target_table_path)
            logger.info(f"Table {table_name} saved to {target_table_path}")
        except Exception as e:
            logger.error(f"Error writing table {table_name} to {target_table_path} failed")
            raise CreateDataFrameError(f"Error writing table {table_name} to {target_table_path}") from e
