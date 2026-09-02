from common.model.base_data_feed_configuration import BaseDataFeedConfiguration
from pydantic import Field


class ModelBase(BaseDataFeedConfiguration):
    source_domain: str = Field(...)
    secondary_lake_location: str = Field(...)
