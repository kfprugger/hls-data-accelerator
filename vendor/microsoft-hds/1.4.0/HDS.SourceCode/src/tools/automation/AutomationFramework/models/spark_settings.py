
import json
from typing import Any, Dict
from environment_publish_state import EnvironmentPublishState

class SparkSettings:
    def __init__(self, properties: Dict[str, Any]):
        """
        Initialize a SparkSettings instance.

        :param state: An instance of EnvironmentPublishState.
        """
        self.state = EnvironmentPublishState(properties.get("state"))
    
    def to_dict(self) -> Dict[str, Any]:

        return {
            "state": self.state.to_dict(),
        }

    def to_json(self) -> str:

        return json.dumps(self.to_dict())

    def __str__(self):
        return self.to_json()