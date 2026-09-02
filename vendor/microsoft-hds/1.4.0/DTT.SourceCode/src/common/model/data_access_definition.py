from posixpath import basename
from typing import Optional

from pydantic import model_validator

from common.model.data_source_type_enum import DataSourceTypeEnum
from common.model.immutable_model import ImmutableModel
from common.model.types import DataSourceId


class DataAccessDefinition(ImmutableModel):
    # For example, a TABLE name
    data_source_id: DataSourceId
    data_source_type: DataSourceTypeEnum
    # For example, a DB name
    data_source_owner_id: Optional[DataSourceId] = None
    data_format: Optional[str] = None

    @model_validator(mode="after")
    def check_data_format(self):
        if not self.data_format and self.data_source_type == DataSourceTypeEnum.STORAGE:
            raise ValueError("data_format cannot be empty")
        return self

    def __str__(self):
        owner_id = (
            basename(self.data_source_owner_id)
            if self.data_source_owner_id
            else self.data_source_owner_id
        )
        return f"[id: {self.data_source_id:.50}, type: {self.data_source_type.name}, owner_id: {owner_id}, format: {self.data_format}]"
