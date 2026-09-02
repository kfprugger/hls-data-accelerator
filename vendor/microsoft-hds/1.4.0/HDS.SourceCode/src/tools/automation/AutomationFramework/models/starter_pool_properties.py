import json
from typing import Any, Dict

class StarterPoolProperties:
    def __init__(self, properties: Dict[str, Any]):
        self.maxExecutors = properties.get("maxExecutors")
        self.maxNodeCount = properties.get("maxNodeCount")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "maxExecutors": self.maxExecutors,
            "maxNodeCount": self.maxNodeCount
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def __str__(self):
        return self.to_json()