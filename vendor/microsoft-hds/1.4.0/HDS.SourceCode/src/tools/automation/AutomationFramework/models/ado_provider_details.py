import json
from typing import Dict
class AdoProviderDetails:
    
    def __init__(
        self,
        properties: Dict):
        
        self.organizationName = properties.get("organizationName", "")
        self.projectName = properties.get("projectName", "")
        self.gitProviderType = properties.get("gitProviderType", "")
        self.repositoryName = properties.get("repositoryName", "")
        self.branchName = properties.get("branchName", "")
        self.directoryName = properties.get("directoryName", "")
    
    def toDict(self):
        
        return {
            "gitProviderDetails": {
                "organizationName":self.organizationName,
                "projectName": self.projectName,
                "gitProviderType":self.gitProviderType,
                "repositoryName": self.repositoryName,
                "branchName":self.branchName,
                "directoryName": self.directoryName, 
            }
        }
    
    def toJson(self):
        return json.dumps(self.toDict())