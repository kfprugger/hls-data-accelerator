import json
from typing import Any, Dict

from .instance_pool import InstancePool
from .starter_pool_properties import StarterPoolProperties

class PoolProperties:
    def __init__(self, properties: Dict[str, Any]):
        self.customizeComputeEnabled: bool = properties.get("customizeComputeEnabled", False)
        self.defaultPool = InstancePool(properties.get("defaultPool", "Starter Pool"))
        self.starterPool = StarterPoolProperties(properties.get("starterPool", {}))

    def to_dict(self) -> Dict[str, Any]:

        return {
            "customizeComputeEnabled": self.customizeComputeEnabled,
            "defaultPool": self.defaultPool.to_dict(),
            "starterPool": self.starterPool.to_dict()
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def __str__(self):
        return self.to_json()