import json
from typing import Any, Dict, List

from .data_pipeline_definition_part import DataPipelineDefinitionPart

class DataPipelineDefinition:
    def __init__(self, data: Dict[str, Any]):
        self.parts: List[DataPipelineDefinitionPart] = [DataPipelineDefinitionPart(part) for part in data.get("parts", [])]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parts": [part.to_dict() for part in self.parts]
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def __str__(self):
        return self.to_json()