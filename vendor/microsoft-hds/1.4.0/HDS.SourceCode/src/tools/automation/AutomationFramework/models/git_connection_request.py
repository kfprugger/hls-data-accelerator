from typing import Dict

class GitConnectionRequest:
    
    def __init__(
        self,
        properties: Dict):
        
        self.gitProviderType = properties.get("gitProviderType", "")
        self.organizationName = properties.get("organizationName", "")
        self.projectName = properties.get("projectName", "")
        self.repositoryName = properties.get("repositoryId", "")
        self.branchName = properties.get("branchName", "")
        self.rootDirectory = properties.get("rootDirectory", "")
        self.isInitialized = properties.get("isIntitialized", False)
    
    def toDict(self):
        
        return {
            "gitProviderType": self.gitProviderType,
            "organizationName":self.organizationName,
            "projectName": self.projectName,
            "repositoryName": self.repositoryName,
            "branchName":self.branchName,
            "rootDirectory": self.rootDirectory,
            "isInitialized": self.isInitialized
        }
        