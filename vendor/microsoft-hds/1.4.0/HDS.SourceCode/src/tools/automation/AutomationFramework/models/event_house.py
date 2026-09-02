import json
from typing import Any, Dict

class EventHouse:
    def __init__(self, data: Dict[str, Any]):
        self.displayName: str = data.get("displayName", "Unknown")
        self.description: str = data.get("description", "No description")
        self.type: str = data.get("type", "Lakehouse")
        self.workspaceId: str = data.get("workspaceId")
        self.id: str = data.get("id")
        self.properties: Any = data.get("properties", {})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "displayName": self.displayName,
            "description": self.description,
            "type": self.type,
            "workspaceId": self.workspaceId,
            "id": self.id,
            "properties": self.properties
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def __str__(self):
        return self.to_json()