import json
from typing import Any, Dict

class EnvironmentProperties:
    def __init__(self, properties: Dict[str, Any]):
        self.name: str = properties.get("name")
        self.runtimeVersion: str = properties.get("runtimeVersion")

    def to_dict(self) -> Dict[str, Any]:

        return {
            "name": self.name,
            "runtimeVersion": self.runtimeVersion
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def __str__(self):
        return self.to_json()