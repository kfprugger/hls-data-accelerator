from typing import Optional, Union

from pydantic import Field

from common.model.immutable_model import ImmutableModel


class ReferenceValuesConfiguration(ImmutableModel):
    secondary_lake_location: str = Field(..., description="secondary lake location")
    source_domain: str = Field(..., description="source mapping domain to use for reference data mappings, e.g., Healthcare,Shared")
    default_value: Optional[Union[int, None]] = Field(None, description="When reference value is not found during transformation,"
                                                      "and failUponMissingReferenceValues is false, DMF will use this value as default value instead ")
    fail_upon_missing_reference_values: bool = Field(False, description="When reference value is not found during transformation, and failUponMissingReferenceValues is false"
                                                     "DMF will fail. If true, DMF will use defaultReferenceValue instead")
