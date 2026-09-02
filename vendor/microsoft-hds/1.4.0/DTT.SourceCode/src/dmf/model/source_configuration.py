from typing import FrozenSet, Generator, Optional

from common.model.base_source_configuration import CommonSourceConfiguration
from pydantic import Field, model_validator

from common.model.data_source_type_enum import DataSourceTypeEnum
from common.model.immutable_model import ImmutableModel
from common.model.types import FeedId
from dmf.model.target_configuration.target_configuration import TargetConfiguration
from dmf.model.target_configuration.target_table_schema import TableColumn
from dmf.model.target_configuration.target_transformation import ColumnTransformation


class SourceTableSchema(ImmutableModel):
    source_modified_date_column_name: str = Field(...)
    source_deleted_status_column_name: Optional[str] = Field(None)
    source_active_status_column_name: Optional[str] = Field(None)
    columns: FrozenSet[TableColumn] = Field(...)


class MappingDefinition(ImmutableModel):
    target_mapping_table_name: str = Field(...)
    source_mapping_table_name: str = Field(...)
    target_id_column_name: str = Field(...)  # Needed for passing top TransformerMetadata
    internal_id_column_name: str = Field(...)  # For example, contact_id
    external_id_column_name: Optional[str] = Field(None)  # For example, integration_key
    db: Optional[str] = Field(None)
    mapping_entity_type: DataSourceTypeEnum = Field(...)
    secondary_lake_location: str = Field(...)

    @model_validator(mode="after")
    def check_self_excluding_values(self):
        if self.mapping_entity_type == DataSourceTypeEnum.STORAGE and self.db:
            raise ValueError("'db' must be empty for STORAGE mapping_entity_type")
        return self

    def __str__(self) -> str:
        source_mapping_table_name = self.source_mapping_table_name if len(
            self.source_mapping_table_name) < 30 else self.source_mapping_table_name[:50] + '...'
        return (
            f"MappingDefinition(target_mapping_table_name={self.target_mapping_table_name}, "
            f"source_table_name={source_mapping_table_name}, "
            f"target_mapping_table_name={self.target_mapping_table_name}, "
            f"target_id_column={self.target_id_column_name}, "
            f"internal_id_column={self.internal_id_column_name}, "
            f"external_id_column={self.external_id_column_name}, "
            f"db={self.db}, "
            f"mapping_entity_type={self.mapping_entity_type.name})")


class SourceConfiguration(CommonSourceConfiguration):
    feed_id: FeedId = Field(...)
    table_schema: Optional[SourceTableSchema] = Field(None)
    target_configurations: FrozenSet[TargetConfiguration] = Field(...)
    mapping_definitions: FrozenSet[MappingDefinition] = Field(...)
    create_view_only: bool = Field(...)
    view_alias: Optional[str] = Field(None)
    source_table_column_name: Optional[str] = Field(default="")
    secondary_lake_location: str = Field(...)

    @property
    def all_column_transformations(self) -> Generator[ColumnTransformation, None, None]:
        """Returns all column mappings for all target configurations"""
        for target_config in self.target_configurations:
            for target_column_transformation in target_config.target_columns_transformations:
                yield target_column_transformation

    @property
    def unique_id(self) -> str:
        return SourceConfiguration.gen_unique_id(self.source_id, self.feed_id)

    @staticmethod
    def gen_unique_id(source_id: str, feed_id: str) -> str:
        return f"{source_id}_{feed_id}"
