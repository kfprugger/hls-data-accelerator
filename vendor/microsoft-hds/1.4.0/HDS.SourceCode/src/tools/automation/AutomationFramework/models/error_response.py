import json
from typing import Any, Dict, List, Optional
from .error_related_resource import ErrorRelatedResource
from .error_response_details import ErrorResponseDetails

class ErrorResponse:
    def __init__(self, properties: Dict[str, Any]):
        self.errorCode = properties.get('errorCode', '')
        self.message = properties.get('message', '')
        self.moreDetails = [ErrorResponseDetails(detail) for detail in properties.get('moreDetails', [])]
        self.relatedResource = ErrorRelatedResource(properties['relatedResource']) if 'relatedResource' in properties else None
        self.requestId = properties.get('requestId', '')
        
    def to_dict(self):
        return {
            "errorCode": self.errorCode,
            "message": self.message,
            "moreDetails": [detail.to_dict() for detail in self.moreDetails],
            "relatedResource": self.relatedResource.to_dict() if self.relatedResource else "",
            "requestId": self.requestId
        }