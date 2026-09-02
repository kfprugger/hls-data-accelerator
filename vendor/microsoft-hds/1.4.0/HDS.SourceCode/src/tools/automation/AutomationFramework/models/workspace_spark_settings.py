import json
from typing import Any, Dict

from .automatic_log_properties import AutomaticLogProperties
from .environment_properties import EnvironmentProperties
from .high_concurrency_properties import HighConcurrencyProperties
from .pool_properties import PoolProperties

class WorkspaceSparkSettings:
    def __init__(self, properties: Dict[str, Any]):

        self.automaticLog = AutomaticLogProperties(properties.get("automaticLog", {}))
        self.environment = EnvironmentProperties(properties.get("environment", {}))
        self.highConcurrency = HighConcurrencyProperties(properties.get("highConcurrency", {}))
        self.pool = PoolProperties(properties.get("pool", {}))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "automaticLog": self.automaticLog.to_dict(),
            "environment": self.environment.to_dict(),
            "highConcurrency": self.highConcurrency.to_dict(),
            "pool": self.pool.to_dict()
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def __str__(self):
        return self.to_json()