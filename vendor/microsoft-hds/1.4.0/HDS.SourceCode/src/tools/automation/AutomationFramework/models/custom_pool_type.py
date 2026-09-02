import json
from typing import Any, Dict

class CustomPoolType:
    def __init__(self, properties: Dict[str, Any]):
        """
        Initialize a CustomPoolType instance.

        :param capacity: The capacity of the custom pool.
        :param workspace: The workspace associated with the custom pool.
        """
        self.capacity: str = properties.get("capacity")
        """The capacity of the custom pool."""

        self.workspace: str = properties.get("workspace")
        """The workspace associated with the custom pool."""

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the CustomPoolType instance to a dictionary.

        :return: Dictionary representation of the instance.
        """
        return {
            "capacity": self.capacity,
            "workspace": self.workspace
        }

    def to_json(self) -> str:
        """
        Serialize the CustomPoolType instance to a JSON string.

        :return: JSON string representation of the instance.
        """
        return json.dumps(self.to_dict())

    def __str__(self):
        return self.to_json()