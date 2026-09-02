import json
from typing import Any, Dict, Optional
from .error_response import ErrorResponse

class ItemJobInstance:

    def __init__(self, properties: Dict[str, Any]):
        self.id = properties.get('id', "")
        self.invokeType = properties.get('invokeType', "")
        self.itemId = properties.get('itemId', "")
        self.jobType = properties.get('jobType', "")
        self.rootActivityId = properties.get('rootActivityId', "")
        self.startTimeUtc = properties.get('startTimeUtc', "")
        self.endTimeUtc = properties.get('endTimeUtc')
        self.status = properties.get('status', "")
        self.failureReason = ErrorResponse(properties['failureReason']) if 'failureReason' in properties and properties['failureReason'] is not None else None
    
    def to_dict(self):
        return {
            "endTimeUtc" : self.endTimeUtc,
            "failureReason" : self.failureReason.to_dict() if self.failureReason is not None else "",
            "id" : self.id,
            "invokeType": self.invokeType,
            "itemId" : self.itemId,
            "jobType" : self.jobType,
            "rootActivityId" : self.rootActivityId,
            "startTimeUtc" : self.startTimeUtc,
            "status" : self.status
        }