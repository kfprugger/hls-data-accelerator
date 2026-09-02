from typing import List

from pydantic import Field

from rmt.contract.configuration.model_base import ModelBase
from rmt.contract.configuration.reference_table import ReferenceTable


class Model(ModelBase):
    reference_tables: List[ReferenceTable] = Field(...)
