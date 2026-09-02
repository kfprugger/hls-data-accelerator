import json
from typing import Any, Dict

class Environment:
    def __init__(self, properties: Dict[str, Any]):

        self.description: str = properties.get("description", "")
        self.displayName: str = properties.get("displayName", "")
        self.id: str = properties.get("id")
        self.properties = properties.get("properties", {})
        self.type = "Environment"
        self.workspaceId: str = properties.get("workspaceId", "")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "displayName": self.displayName,
            "id": self.id,
            "properties": self.properties,
            "type": self.type,
            "workspaceId": self.workspaceId
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def __str__(self):
        return self.to_json()