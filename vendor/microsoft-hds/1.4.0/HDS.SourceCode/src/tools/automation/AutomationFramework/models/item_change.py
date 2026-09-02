import json
from typing import Any, Dict
from .item_metadata import ItemMetadata

class ItemChange:

    def __init__(self, properties: Dict[str, str]):
        self.conflictType: str = properties.get("conflictType", "")
        self.remoteChange: str = properties.get("remoteChange", "")
        self.workspaceChange: str = properties.get("workspaceChange", "")
        self.itemMetadata: ItemMetadata = ItemMetadata(properties.get("itemMetadata", {}))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conflictType": self.conflictType,
            "remoteChange": self.remoteChange,
            "workspaceChange": self.workspaceChange,
            "itemMetadata": self.itemMetadata.to_dict()
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def __str__(self):
        return self.to_json()