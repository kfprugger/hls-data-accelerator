from typing import Any, Dict

class ErrorResponseDetails:
    code: str
    message: str

    def __init__(self, properties: Dict[str, Any]) -> None:
        self.code = properties.get('code', '')
        self.message = properties.get('message', '')
    
    def to_dict(self):
        return {
            "code": self.code,
            "message": self.message
        }