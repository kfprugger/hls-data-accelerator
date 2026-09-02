import json
from typing import Any, Dict

class UpdateFromGitRequest:
    def __init__(self, properties: Dict[str, Any]):
        self.remoteCommitHash = properties.get('remoteCommitHash', '')
        self.conflictResolution = properties.get('conflictResolution', '')
        self.options = properties.get('options', '')
        self.workspaceHead = properties.get('workspaceHead', '')

    def to_dict(self) -> Dict[str, Any]:
        return {
            'remoteCommitHash': self.remoteCommitHash,
            'conflictResolution': self.conflictResolution,
            'options': self.options,
            'workspaceHead': self.workspaceHead
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=4)