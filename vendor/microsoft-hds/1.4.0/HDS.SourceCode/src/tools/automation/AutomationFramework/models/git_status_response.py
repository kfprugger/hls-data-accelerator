import json
from typing import Any, Dict, List
from .item_change import ItemChange
from .item_identifier import ItemIdentifier

class GitStatusResponse:

    def __init__(self, properties: Dict[str, str]):
        self.remoteCommitHash: str = properties.get("remoteCommitHash", "")
        self.workspaceHead: str = properties.get("workspaceHead", "")
        self.changes: List[ItemChange] = [ItemChange(s) for s in properties.get("changes", [])]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "remoteCommitHash": self.remoteCommitHash,
            "workspaceHead": self.workspaceHead,
            "itemIdentifier": [c.to_dict() for c in self.changes]
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def __str__(self):
        return self.to_json()