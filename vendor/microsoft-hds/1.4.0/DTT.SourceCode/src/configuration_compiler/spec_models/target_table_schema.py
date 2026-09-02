from pydantic import Field
from dmf.model.target_configuration.target_table_schema import TargetTableColumn, TargetTableSchema


class TargetTableSchemaExt(TargetTableSchema):
    description: str = Field(...)


class TargetTableColumnExt(TargetTableColumn):
    description: str = Field(...)
    is_fk: bool = Field(...)
