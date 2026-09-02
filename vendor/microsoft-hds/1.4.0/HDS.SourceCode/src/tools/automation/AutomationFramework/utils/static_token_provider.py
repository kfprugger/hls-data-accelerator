from utils.token_provider import TokenProvider

class StaticTokenProvider(TokenProvider):
    def __init__(self, token):
        self.token = token

    def get_token(self):
        return self.token