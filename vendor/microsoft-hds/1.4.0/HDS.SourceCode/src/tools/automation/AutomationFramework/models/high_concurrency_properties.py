import json
from typing import Any, Dict

class HighConcurrencyProperties:
    def __init__(self, properties: Dict[str, Any]):
        self.notebookInteractiveRunEnabled: bool = properties.get("notebookInteractiveRunEnabled", False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "notebookInteractiveRunEnabled": self.notebookInteractiveRunEnabled
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def __str__(self):
        return self.to_json()