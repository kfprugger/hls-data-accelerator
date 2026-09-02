import json
from typing import FrozenSet

from common.model.base_data_feed_configuration import BaseDataFeedConfiguration
from pydantic import Field

from common.model.types import FeedId
from dmf.model.reference_values_configuration import ReferenceValuesConfiguration
from dmf.model.source_configuration import SourceConfiguration


class DataFeedConfiguration(BaseDataFeedConfiguration):
    feed_id: FeedId = Field(..., description="Feed Id")
    source_configurations: FrozenSet[SourceConfiguration] = Field(..., description="source_configurations")
    reference_values_configuration: ReferenceValuesConfiguration = Field(..., description="reference_values_configuration")

    @classmethod
    def from_str(cls, transformation_spec_content: str) -> "DataFeedConfiguration":
        try:
            return cls(**json.loads(transformation_spec_content))
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse transformation spec Json: {e}")
