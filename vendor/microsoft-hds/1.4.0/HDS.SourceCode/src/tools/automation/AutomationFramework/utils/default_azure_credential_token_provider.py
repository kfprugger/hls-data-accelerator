import time
import jwt
from azure.identity import DefaultAzureCredential
from .token_provider import TokenProvider

class DefaultAzureCredentialTokenProvider(TokenProvider):
    
    def __init__(self):
        self.token = None
        # CodeQL [SM05139] This is non-production testing code which is not deployed.
        self.credential = DefaultAzureCredential()

    def get_token(self):
        if self.token is None or self.is_token_expired():
            self.refresh_token()
        return self.token

    def is_token_expired(self):
        try:
            decoded_token = jwt.decode(self.token, algorithms=None, options={'verify_signature': False})
            exp = decoded_token.get("exp", 0)
            current_time = time.time()
            return current_time >= exp
        except Exception as e:
            print(f"Error decoding token: {e}")
            return True

    def refresh_token(self):
        # Implement the logic to refresh the token here
        print("Refreshing token...")
        # CodeQL [SM05139] This is non-production testing code which is not deployed.
        credential = DefaultAzureCredential()

        # Get the access token for Power BI
        scopes = [
            "https://analysis.windows.net/powerbi/api",
        ]

        self.token = credential.get_token(*scopes).token