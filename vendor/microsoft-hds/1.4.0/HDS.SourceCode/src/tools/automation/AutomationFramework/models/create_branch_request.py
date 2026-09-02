import json
from typing import Dict

class CreateBranchRequest:
    
    def __init__(
        self,
        properties: Dict):
        
        self.branchName = properties.get("branchName", "")
        self.parentBranchName = properties.get("parentBranchName", "")
        self.organizationName = properties.get("organizationName", "")
        self.projectName = properties.get("projectName", "")
        self.providerType = properties.get("providerType", "")
        self.repositoryId = properties.get("repositoryId", "")
        self.workspaceId = properties.get("workspaceId", "")
    
    def toDict(self):
        
        return {
            "branchName":self.branchName,
            "parentBranchName": self.parentBranchName,
            "organizationName":self.organizationName,
            "projectName": self.projectName,
            "providerType": self.providerType,
            "repositoryId": self.repositoryId,
            "workspaceId": self.workspaceId
        }
    
    def toJson(self):
        return json.dumps(self.toDict())
        