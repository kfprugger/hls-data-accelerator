import json

class CreateDataPipelineRequest:
    def __init__(self, displayName: str, description: str):
        if len(displayName) > 256:
            raise ValueError("The display name cannot contain more than 256 characters.")
        if displayName == "Admin monitoring":
            raise ValueError('"Admin monitoring" is a reserved workspace name.')
        
        if len(description) > 4000:
            raise ValueError("The description cannot contain more than 4000 characters.")
        
        self.displayName = displayName
        self.description = description

    def to_dict(self) -> dict:
        return {
            'displayName': self.displayName,
            'description': self.description
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def __str__(self):
        return self.to_json()
