from typing import Dict, FrozenSet, List, Tuple

from pyspark.sql import DataFrame

from dmf.transformations.model.transformation_types import Source2TargetIdMapping


class SourceSchemaManipulator:

    @staticmethod
    def adjust_to_target(source_df: DataFrame,
                         source_to_target_columns_mapping: Dict[str, List[str]],
                         synthetically_nulled_primary_keys: FrozenSet[str],
                         target_types: List[Tuple[str, str]],
                         target_table: str,
                         source_to_target_ids_mapping: List[Source2TargetIdMapping],
                         partition_column_names: List[str]) -> DataFrame:

        df, source_to_target_mapped_columns = SourceSchemaManipulator._adjust_transformed_columns_to_target(
            source_df, source_to_target_columns_mapping, target_types, target_table, partition_column_names
        )

        df = SourceSchemaManipulator._add_nulled_columns(
            df, synthetically_nulled_primary_keys, target_types, target_table
        )

        remaining_target_columns = (set([target_field for target_field, _ in target_types]) -
                                    set(source_df.columns) -
                                    set(source_to_target_mapped_columns) -
                                    set(synthetically_nulled_primary_keys) -
                                    set(partition_column_names))
        mapped_id_columns = [id_mapping.source_id_col_name for id_mapping in source_to_target_ids_mapping]
        remaining_target_columns = remaining_target_columns - set(mapped_id_columns)

        df = SourceSchemaManipulator._add_nulled_columns(
            df, frozenset(remaining_target_columns), target_types, target_table
        )

        return df

    @staticmethod
    def _add_nulled_columns(source_df: DataFrame,
                            nulled_columns: FrozenSet[str],
                            target_types: List[Tuple[str, str]],
                            target_table: str) -> DataFrame:
        expressions = []
        target_types_dict = dict(target_types)
        for target_field in nulled_columns:
            if target_field not in target_types_dict:
                raise ValueError(
                    f"Target field {target_field} is missing in target table [{target_table}]."
                )
            expressions.append(f"CAST(NULL AS {target_types_dict[target_field]}) AS {target_field}")

        return source_df.selectExpr('*', *expressions)

    @staticmethod
    def _adjust_transformed_columns_to_target(source_df: DataFrame,
                                              source_to_target_columns_mapping: Dict[str, List[str]],
                                              target_types: List[Tuple[str, str]],
                                              target_table: str,
                                              partition_column_names: List[str]) -> Tuple[DataFrame, List[str]]:
        expressions = []
        mapped_columns = []
        target_types_dict = dict(target_types)

        for source_field in source_df.columns:
            if source_field in source_to_target_columns_mapping:
                for target_field in source_to_target_columns_mapping[source_field]:
                    if target_field not in target_types_dict:
                        if target_field in partition_column_names:
                            continue
                        raise ValueError(
                            f"Target field {target_field} is missing in target table [{target_table}]. "
                            f"source field:{source_field}"
                        )
                    expressions.append(f"CAST({source_field} AS {target_types_dict[target_field]}) AS {target_field}")
                    mapped_columns.append(target_field)
            else:
                expressions.append(source_field)

        return source_df.selectExpr(expressions), mapped_columns
