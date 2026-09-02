from typing import Dict

class ErrorRelatedResource:
    resourceType: str
    resourceId: str
    
    def __init__(self, data: Dict) -> None:
        self.resourceType = data.get('resourceType', "")
        self.resourceId = data.get('resourceId', "")
    
    def to_dict(self):
        return {
            "resourceType": self.resourceType,
            "resourceId": self.resourceId
        }