import json
from typing import Any, Dict

class Notebook:
    def __init__(self, properties: Dict[str, Any]):

        self.description: str = properties.get("description", "")
        self.displayName: str = properties.get("displayName", "")
        self.id: str = properties.get("id", "")
        self.type: str = properties.get("type", "Notebook")
        self.workspaceId: str = properties.get("workspaceId", "")

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the Notebook instance to a dictionary.

        :return: Dictionary representation of the instance.
        """
        return {
            "description": self.description,
            "displayName": self.displayName,
            "id": self.id,
            "type": self.type,  # Assuming ItemType has a proper representation
            "workspaceId": self.workspaceId
        }

    def to_json(self) -> str:
        """
        Serialize the Notebook instance to a JSON string.

        :return: JSON string representation of the instance.
        """
        return json.dumps(self.to_dict())

    def __str__(self):
        return self.to_json()