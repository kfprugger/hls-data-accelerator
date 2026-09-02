import json
from typing import Any, Dict

class Capacity:
    def __init__(self, data: Dict[str, Any]):
        self.id = data.get("id")
        self.name = data.get("name")
        self.status = data.get("status")
        self.displayName = data.get("displayName", "Unknown")
        self.sku = data.get("sku", "Unknown")
        self.region = data.get("region", "Unknown")
        self.state = data.get("state", "Unknown")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "displayName": self.displayName,
            "sku": self.sku,
            "region": self.region,
            "state": self.state
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def __str__(self):
        return self.to_json()