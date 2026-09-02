import json
from typing import Any, Dict, List
from .event_stream_definition_part import EventStreamDefinitionPart

class EventStreamDefinition:
    def __init__(self, data: Dict[str, Any]):
        definition = data.get("definition")
        self.parts: List[EventStreamDefinitionPart] = [EventStreamDefinitionPart(part) for part in definition.get("parts", [])]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parts": [part.to_dict() for part in self.parts]
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def __str__(self):
        return self.to_json()