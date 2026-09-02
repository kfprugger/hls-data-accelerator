from typing import FrozenSet

from pydantic import Field

from common.model.base_source_configuration import BaseSourceConfiguration
from common.model.immutable_model import ImmutableModel


class BaseDataFeedConfiguration(ImmutableModel):
    source_configurations: FrozenSet[BaseSourceConfiguration] = Field(..., description="source_configurations")
