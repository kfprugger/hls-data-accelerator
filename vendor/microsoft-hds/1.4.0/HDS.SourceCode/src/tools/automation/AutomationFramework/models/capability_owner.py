class CapabilityOwner:
    objectId: str
    name: str
    userPrincipalName: str

    def __init__(self, properties: dict):
        self.objectId = properties.get('objectId', '')
        self.name = properties.get('name', '')
        self.userPrincipalName = properties.get('userPrincipalName', '')

    def toDict(self):
        return {
            'objectId': self.objectId,
            'name': self.name,
            'userPrincipalName': self.userPrincipalName
        }