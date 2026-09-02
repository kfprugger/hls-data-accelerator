from .deployed_artifact import DeployedArtifact
from .capability_owner import CapabilityOwner

class CapabilityResponse:
    def __init__(self, data: dict):
        self.provisionState = data.get('provisionState', '')
        self.deployedArtifacts = [DeployedArtifact(v) for k, v in data.get('deployedArtifacts', {}).items()]
        self.createdDate = data.get('createdDate', '')
        self.lastUpdatedDate = data.get('lastUpdatedDate', '')
        self.ownerUser = CapabilityOwner(data.get('ownerUser', {}))
        self.name = data.get('name', '')
        self.version = data.get('version', '')
        
    def toDict(self):
        return {
            "provisionState": self.provisionState,
            "deployedArtifacts": [artifact.toDict() for artifact in self.deployedArtifacts],
            "createdDate": self.createdDate,
            "lastUpdatedDate": self.lastUpdatedDate,
            "ownerUser": self.ownerUser.toDict(),
            "name": self.name,
            "version": self.version
        }