import json
from typing import Any, Dict

class EventHouseDefinitionPart:
    def __init__(self, data: Dict[str, Any]):
        self.path: str = data.get("path", "Unknown")
        self.payload: str = data.get("payload", "")
        self.payloadType: str = data.get("payloadType", "InlineBase64")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "payload": self.payload,
            "payloadType": self.payloadType
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def __str__(self):
        return self.to_json()