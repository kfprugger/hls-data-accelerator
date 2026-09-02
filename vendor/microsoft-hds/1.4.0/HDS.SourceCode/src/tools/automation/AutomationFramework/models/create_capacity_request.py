import json
from typing import Dict, Optional

class CreateCapacityRequest:
    
    def __init__(self, subscriptionId, resourceGroupName, capacityName, size, admin, location) -> None:
        self.subscriptionId: Optional[str] = subscriptionId
        self.resourceGroupName: Optional[str] = resourceGroupName
        self.capacityName: Optional[str] = capacityName
        self.size: Optional[str] = size
        self.admin: Optional[str] = admin
        self.location: Optional[str] = location

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {
            'subscriptionId': self.subscriptionId,
            'resourceGroupName': self.resourceGroupName,
            'capacityName': self.capacityName,
            'size': self.size,
            'admin': self.admin,
            'location': self.location
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def __str__(self):
        return self.to_json()