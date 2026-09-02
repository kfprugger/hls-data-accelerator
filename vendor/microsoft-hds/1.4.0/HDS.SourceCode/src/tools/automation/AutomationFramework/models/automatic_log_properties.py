import json
from typing import Any, Dict

class AutomaticLogProperties:
    def __init__(self,  properties: Dict[str, Any]):
        self.enabled: bool = properties.get("enabled")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def __str__(self):
        return self.to_json()