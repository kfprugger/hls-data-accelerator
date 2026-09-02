import json
from typing import Any, Dict

class DataPipeline:
    def __init__(self, properties: Dict[str, Any]):

        self.description: str = properties.get("description", "")
        self.displayName: str = properties.get("displayName", "")
        self.id: str = properties.get("id")
        self.type = "DataPipeline"
        self.workspaceId: str = properties.get("workspaceId", "")
        
        if isinstance(self.id, list):
            self.id = self.id[0]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "displayName": self.displayName,
            "id": self.id,
            "type": self.type,
            "workspaceId": self.workspaceId
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def __str__(self):
        return self.to_json()