import json
from typing import Any, Dict

class InstancePool:
    def __init__(self, properties: Dict[str, Any]):
        self.id: str = properties.get("id", "")
        self.name: str = properties.get("name")
        self.type: str = properties.get("type")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def __str__(self):
        return self.to_json()