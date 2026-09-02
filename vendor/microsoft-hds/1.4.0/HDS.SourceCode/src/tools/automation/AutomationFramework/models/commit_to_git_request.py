import json
from typing import Any, Dict
from .item_identifier import ItemIdentifier

class CommitToGitRequest:
    def __init__(self, properties: Dict[str, Any]):
        self.mode = properties.get('mode', True)
        self.comment = properties.get('comment', '')
        self.artifacts = [ItemIdentifier(item['path']) for item in properties.get('items', [])]
        self.workspaceHead = properties.get('workspaceHead', '')

    def toDict(self) -> Dict[str, Any]:
        return {
            'mode': self.mode,
            'comment': self.comment,
            'artifacts': [item.to_dict() for item in self.artifacts],
            'workspaceHead': self.workspaceHead
        }

    def toJson(self) -> str:
        return json.dumps(self.toDict(), indent=4)