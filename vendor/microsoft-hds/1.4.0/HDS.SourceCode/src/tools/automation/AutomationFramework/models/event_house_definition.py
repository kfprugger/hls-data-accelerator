import json
from typing import Any, Dict, List
from .event_house_definition_part import EventHouseDefinitionPart

class EventHouseDefinition:
    def __init__(self, data: Dict[str, Any]):
        self.format: str = data.get("format", "Unknown")
        self.parts: List[EventHouseDefinitionPart] = [EventHouseDefinitionPart(part) for part in data.get("parts", [])]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "format": self.format,
            "parts": [part.to_dict() for part in self.parts]
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def __str__(self):
        return self.to_json()