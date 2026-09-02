from typing import Any

class CapabilityParameter:
    
    def __init__(self, properties: dict[str, Any]):
        self.name = properties.get("name", "Local")
        self.value = properties.get("value", "Local")
        self.type = properties.get("Type", "Local") # Local or Global
    
    def toDict(self):
        return {
            "Name": self.name,
            "Value": self.value,
            "Type": self.type
        }