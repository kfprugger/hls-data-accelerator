import json
from typing import Any, Dict

class AzureDevOpsDetails:
    def __init__(self, properties: Dict[str, Any]):
        self.branchName = properties.get('branchName', '')
        self.directoryName = properties.get('directoryName', '')
        self.gitProviderType = properties.get('gitProviderType', 'AzureDevOps')
        self.organizationName = properties.get('organizationName', '')
        self.projectName = properties.get('projectName', '')
        self.repositoryName = properties.get('repositoryName', '')

    def to_dict(self) -> Dict[str, Any]:
        return {
            'branchName': self.branchName,
            'directoryName': self.directoryName,
            'gitProviderType': self.gitProviderType,
            'organizationName': self.organizationName,
            'projectName': self.projectName,
            'repositoryName': self.repositoryName
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)