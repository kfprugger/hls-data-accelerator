import json
from typing import Any, Dict

from .notebook_definition import NotebookDefinition

class CreateNotebookRequest:
    def __init__(self, properties: Dict[str, Any]):

        self.definition = NotebookDefinition(properties.get("definition"))
        self.description: str = properties.get("description")
        self.displayName: str =  properties.get("displayName")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "definition": self.definition.to_dict(),  # Assuming NotebookDefinition has a proper representation
            "description": self.description,
            "displayName": self.displayName
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def __str__(self):
        return self.to_json()