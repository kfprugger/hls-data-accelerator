import json
from typing import Any, Dict

class EnvironmentPublishState:
    def __init__(self, properties: Dict[str, Any]):

        self.Cancelled: str = properties.get("Cancelled")
        self.Cancelling: str = properties.get("Cancelling")
        self.Failed: str = properties.get("Failed")
        self.Running: str = properties.get("Running")
        self.Success: str = properties.get("Success")
        self.Waiting: str = properties.get("Waiting")

    def to_dict(self) -> Dict[str, Any]:

        return {
            "Cancelled": self.Cancelled,
            "Cancelling": self.Cancelling,
            "Failed": self.Failed,
            "Running": self.Running,
            "Success": self.Success,
            "Waiting": self.Waiting
        }

    def to_json(self) -> str:

        return json.dumps(self.to_dict())

    def __str__(self):
        return self.to_json()