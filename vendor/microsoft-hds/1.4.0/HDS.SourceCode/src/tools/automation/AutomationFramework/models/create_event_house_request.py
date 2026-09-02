import json

class CreateEventHouseRequest:
    def __init__(self, displayName: str, description: str):
        self.displayName = displayName
        self.description = description

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def __str__(self):
        return self.to_json()

    def to_dict(self) -> dict:
        return {
            'displayName': self.displayName,
            'description': self.description
        }