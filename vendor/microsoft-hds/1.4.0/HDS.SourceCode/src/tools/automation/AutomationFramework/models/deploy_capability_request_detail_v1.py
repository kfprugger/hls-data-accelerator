from typing import List, Any
from .capability_parameter import CapabilityParameter

class DeployCapabilityRequestDetailV1:

    def __init__(self, properties: dict[str, Any]):

        self.capabilities = properties.get("capabilities")
        self.uniquePrefix = properties.get("uniquePrefix", "")
        self.userParameters = [CapabilityParameter(p) for p in properties.get("userParameters", [])]

    def toDict(self):
        return {
          "Capabilities": self.capabilities,
          "UniquePrefix": self.uniquePrefix,
          "UserParameters": [p.toDict() for p in self.userParameters]
        }