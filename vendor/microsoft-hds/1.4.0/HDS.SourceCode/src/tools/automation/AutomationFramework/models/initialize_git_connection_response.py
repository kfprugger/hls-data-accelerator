import json
from typing import Any, Dict

class InitializeGitConnectionResponse:
    def __init__(self, properties: Dict[str, Any]):
        self.remoteCommitHash = properties.get('remoteCommitHash', '')
        self.requiredAction = properties.get('requiredAction', '')
        self.workspaceHead = properties.get('workspaceHead', '')

    def to_dict(self) -> Dict[str, Any]:
        return {
            'remoteCommitHash': self.remoteCommitHash,
            'requiredAction': self.requiredAction,
            'workspaceHead': self.workspaceHead
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=4)