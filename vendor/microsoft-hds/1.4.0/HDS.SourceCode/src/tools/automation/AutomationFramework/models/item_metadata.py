import json
from typing import Any, Dict
from .item_identifier import ItemIdentifier

class ItemMetadata:

    def __init__(self, properties: Dict[str, str]):
        self.displayName: str = properties.get("displayName", "")
        self.itemType: str = properties.get("itemType", "")
        self.itemIdentifier: ItemIdentifier = ItemIdentifier(properties.get("itemIdentifier", {}))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "displayName": self.displayName,
            "itemType": self.itemType,
            "itemIdentifier": self.itemIdentifier.to_dict()
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def __str__(self):
        return self.to_json()