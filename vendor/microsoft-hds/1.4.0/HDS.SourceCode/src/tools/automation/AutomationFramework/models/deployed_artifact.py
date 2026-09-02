import json

class DeployedArtifact:
    def __init__(self, properties: dict):
        self.objectId = properties.get('objectId', '')
        self.provisionState = properties.get('provisionState', '')
        self.artifactKey = properties.get('artifactKey', '')
        self.displayName = properties.get('displayName', '')
        self.version = properties.get('version', '')
        self.artifactType = properties.get('artifactType', '')

    def toDict(self):
        return {
            'objectId': self.objectId,
            'provisionState': self.provisionState,
            'artifactKey': self.artifactKey,
            'displayName': self.displayName,
            'version': self.version,
            'artifactType': self.artifactType
        }
    
    