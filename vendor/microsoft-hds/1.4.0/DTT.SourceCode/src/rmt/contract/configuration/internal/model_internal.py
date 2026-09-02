from typing import Dict

from pydantic import Field

from rmt.contract.configuration.model_base import ModelBase
from rmt.contract.configuration.reference_table import ReferenceTable


class ModelInternal(ModelBase):
    reference_tables: Dict[str, ReferenceTable] = Field(...)

    def __init__(self, **data):
        ref_tables_list = data.pop("reference_tables")
        formatted_ref_tables = {ref_table["table_name"]: ReferenceTable(**ref_table) for ref_table in ref_tables_list}
        super().__init__(reference_tables=formatted_ref_tables, **data)
