import json
from typing import Any, Dict

class ItemIdentifier:

    def __init__(self, properties: Dict[str, str]):
        self.logicalId: str = properties.get("logicalId", "")
        self.objectId: str = properties.get("objectId", "")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "logicalId": self.logicalId,
            "objectId": self.objectId
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def __str__(self):
        return self.to_json()