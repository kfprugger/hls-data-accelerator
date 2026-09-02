from typing import List, Optional

from common.utils.logging import Logger
from delta import DeltaTable
from pyspark.sql import DataFrame

from dmf.utils.common import Common
from dmf.transformations.writer.writer import Writer
from dmf.utils.logging_utils import Timed


class DeltaTableUpsertWriter(Writer):
    def __init__(self, location: str, id,
                 target_all_column_names: List[str],
                 target_key_column_names: Optional[List[str]] = None):

        if not location:
            raise ValueError("Location is not provided")

        if not target_all_column_names:
            raise ValueError("Target table full columns list must be provided")
        if not target_key_column_names:
            raise ValueError("Target primary key column names must be provided")

        super().__init__(id)
        self.location: str = location
        self.target_all_column_names: List[str] = target_all_column_names
        self.target_key_column_names: List[str] = target_key_column_names

    def __str__(self) -> str:
        return f"DeltaTableWriter[{self.id}]"

    @Timed(Logger)
    def write(self,
              df: DataFrame,
              partition_column: Optional[str] = None) -> None:

        if not df:
            raise ValueError("DataFrame containing data to write cannot be None")
        if partition_column and partition_column not in df.columns:
            raise ValueError(f"Partition column '{partition_column}' does not exist in the DataFrame to write")
        elif not partition_column:
            Logger.info(f"Partition column is not provided for writing to {self}")

        target_delta_table = DeltaTable.forPath(df.sparkSession, self.location)
        source_to_target_comparison_condition = self._build_comparison_condition(self.target_key_column_names)
        update_columns = {column_name: f"source.{column_name}" for column_name in self.target_all_column_names
                          if column_name and column_name not in self.target_key_column_names}
        writable_columns_dict = {column_name: f"source.{column_name}" for column_name in self.target_all_column_names
                                 if column_name}
        partition_columns_dict = {partition_column: f"source.{partition_column}"} if partition_column else {}
        insert_columns = {**writable_columns_dict, **partition_columns_dict}

        try:
            target_delta_table.alias("target").merge(
                source=df.alias("source"),
                condition=source_to_target_comparison_condition
            ).whenMatchedUpdate(
                set=update_columns
            ).whenNotMatchedInsert(
                values=insert_columns
            ).execute()
        except Exception as e:
            Logger.error(f"Error while writing data to {self.location}. "
                         f"Context: {self}: {e}")
            raise

    def _build_comparison_condition(self, target_key_column_names: List[str]) -> str:
        spark_sql_null_safe_equal_operator = "<=>"

        condition = Common.build_and_condition_from_list(
            conditional_values=target_key_column_names,
            left_prefix="target",
            right_prefix="source",
            comparison=spark_sql_null_safe_equal_operator)

        if not condition:
            raise ValueError("Comparison condition was not generated.")

        Logger.info(f"{self} built the following comparison condition: {condition}")

        return condition
