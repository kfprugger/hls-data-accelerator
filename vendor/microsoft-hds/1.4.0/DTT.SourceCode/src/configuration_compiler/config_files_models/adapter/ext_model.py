from collections import defaultdict
import json
from typing import Optional

from configuration_compiler.config_files_models.adapter.model import RawAdapterModel, SourceField, SourceTable
from common.model.types import DataSourceId, TargetId


class AdapterModel(RawAdapterModel):
    @classmethod
    def from_str(cls, dmf_adaptor: str) -> "AdapterModel":
        try:
            return cls(**json.loads(dmf_adaptor))
        except json.JSONDecodeError as e:
            raise ValueError("Failed to parse the DMF adapter:") from e

    def source_db_name(self) -> Optional[str]:
        return self.source.lakeDBName

    @property
    def source_tables(self):
        for source_table in self.sourceTables:
            if source_table.enabled:
                yield source_table

    def source_fields_on_source_table(self, source_table: SourceTable):
        for source_field in source_table.sourceFields:
            if source_field.enabled:
                yield source_field

    @property
    def target_fields(self):
        for source_table in self.source_tables:
            for source_field in source_table.sourceFields:
                if source_field.enabled:
                    if source_field.targetFields.fields is not None:
                        for target_field in source_field.targetFields.fields:
                            if target_field.enabled:
                                yield source_table, source_field, target_field

    def target_fields_on_source_field(self, source_field: SourceField):
        fields = source_field.targetFields.fields
        if fields is not None:
            for target_field in fields:
                if target_field.enabled:
                    yield target_field

    @property
    def target_table_paths(self) -> dict[DataSourceId, dict[TargetId, list[TargetId]]]:
        """
        Compute the target table paths` overrides for each source table
        the values are of the form {target_table: [tables]}
        """
        mapping = defaultdict(lambda: defaultdict(list))
        for source_table, _, target_field in self.target_fields:
            for path in target_field.paths or []:
                mapping[source_table.tableName][target_field.tableName].append(path)

        return dict(mapping)
