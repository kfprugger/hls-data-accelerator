from configuration_compiler.config_files_models.semantics.model import DurationTable
from dmf.model.target_configuration.target_table_schema import DurationTableSemantics


def from_DurationTable(dt: DurationTable) -> DurationTableSemantics:
    return DurationTableSemantics(
        name=dt.table,
        start_col_name=dt.startField,
        end_col_name=dt.endField,
        group_by_cols=frozenset(dt.groupBy),
    )
