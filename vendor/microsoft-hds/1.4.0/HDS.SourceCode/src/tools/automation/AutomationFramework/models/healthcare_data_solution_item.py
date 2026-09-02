import json
from typing import Any, Dict

class HealthcareDataSolutionItem:
    
    def __init__(self, data: Dict[str, Any]):
        self.id = data.get("id")
        self.displayName = data.get("displayName", "Unknown")
        self.description = data.get("description", "No description")
        self.type = data.get("type", "Unknown")
        self.workspaceId = data.get("workspaceId", "")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "displayName": self.displayName,
            "description": self.description,
            "type": self.type,
            "workspaceId": self.workspaceId
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def __str__(self):
        return self.to_json()