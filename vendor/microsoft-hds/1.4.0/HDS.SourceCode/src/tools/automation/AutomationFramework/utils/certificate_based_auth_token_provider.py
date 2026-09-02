import os
import subprocess
import time
import jwt
import shutil
from .config_utility import load_config
from .token_provider import TokenProvider

class CertificateBasedAuthTokenProvider(TokenProvider):
    
    fabricClientId = "871c010f-5e61-4fb1-83ac-98610a7e9110"
    fabricScopes = "https://analysis.windows.net/powerbi/api/.default"
    capacityManagementRedirectUri = "https://portal.azure.com/auth/login/"
    capacityManagementClientId  = "c44b4083-3bb0-49c1-b47d-974e53cbdf3c"
    capacityManagementScopes = "https://management.azure.com/.default"
    capacityManagementRedirectUri = "https://portal.azure.com/auth/login/"
    storageScope = "https://storage.azure.com/.default"

    def __init__(self, config):
        configBaseDirectory = os.path.join(os.path.dirname(__file__).split("/utils")[0], "config")
        self.token = None
        utilsDir = os.path.dirname(os.path.realpath(__file__))
        self.exePath = os.path.join(utilsDir, "cba_token_provider/SilentCertificateBasedAuthenticator")

        self.tenantId = config["tenantId"]
        self.redirectUri = config["redirectUri"]
        self.userName = config["userDetails"]["userName"]
        self.certificateName = config["userDetails"]["certificateFileName"]
        #self.targetEnvironment = config["targetEnvironment"]
        certificatefileSource = os.path.join(configBaseDirectory, self.certificateName)
        certificatefileDestination = os.path.join(utilsDir, "cba_token_provider")
        shutil.copy(certificatefileSource, certificatefileDestination)

    def get_token(self):
        if self.token is None:
            print("Getting token...")
            self.refresh_token()
        elif self.is_token_expired():
            print("Token expired. Refreshing token...")
            self.refresh_token()
        return self.token

    def is_token_expired(self):
        try:
            decoded_token = jwt.decode(self.token, algorithms=None, options={'verify_signature': False})
            exp = decoded_token.get("exp", 0)
            current_time = time.time()
            return current_time >= exp - 60
        except Exception as e:
            print(f"Error decoding token: {e}")
            return True

    def refresh_token(self):
        os.system("chmod +x " + self.exePath)
        self.token = subprocess.check_output(self.exePath + " " + self.tenantId + " " + self.fabricClientId +" "+ self.redirectUri + " " +
                                            self.userName + " " + self.certificateName + " " + self.fabricScopes, shell=True, text=True)

    def get_azure_management_token(self):
        os.system("chmod +x " + self.exePath)
        return subprocess.check_output(self.exePath + " " + self.tenantId + " " + self.capacityManagementClientId +" "+ self.capacityManagementRedirectUri + " " +
                                            self.userName + " " + self.certificateName + " " + self.capacityManagementScopes, shell=True, text=True)

    def get_storage_token(self):
        os.system("chmod +x " + self.exePath)
        return subprocess.check_output(self.exePath + " " + self.tenantId + " " + self.fabricClientId +" "+ self.redirectUri + " " +
                                            self.userName + " " + self.certificateName + " " + self.storageScope, shell=True, text=True)
