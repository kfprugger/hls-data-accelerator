import json
from time import sleep
import requests
from typing import List

from utils.token_provider import TokenProvider
from .client_utils import handle_list_response
from models.capacity import Capacity
from models.create_capacity_request import CreateCapacityRequest
from logging import Logger
from .client_utils import handle_list_response, handle_response
from utils.certificate_based_auth_token_provider import CertificateBasedAuthTokenProvider


allowed_capacity_skus = [
    "F2",
    "F4",
    "F8",
    "F16",
    "F32",
    "F64",
    "F128",
    "F256",
    "F512",
    "F1024",
    "F2048"
]

class CapacityClient:

    def __init__(self, token_provider: TokenProvider, env="msit", logger: Logger = None):
        self.token_provider = token_provider
        self.endpoint = f"https://{env}api.fabric.microsoft.com/v1/capacities"
        self.management_endpoint = "https://management.azure.com/subscriptions"
        self.logger = logger

    def validate_capacity_size(self, size: str):
        if size not in allowed_capacity_skus:
            raise ValueError(f"Capacity size must be one of {allowed_capacity_skus}")
        
    def get_capacity(self, capacityId: str) -> Capacity:
        token = self.token_provider.get_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        response = requests.get(self.endpoint, headers=headers)
        capacities = handle_list_response(response, Capacity)
        for capacity in capacities:
            if capacity.id == capacityId:
                return capacity

    def get_capacities(self) -> List[Capacity]:
        headers = {"Authorization": f"Bearer {self.get_azure_management_token()}", "Content-Type": "application/json"}
        response = requests.get(self.endpoint, headers=headers)
        return handle_list_response(response, Capacity)

    def pause_capacity(self, capacityName: str, subscriptionId: str, resourceGroupName: str):
        headers = {"Authorization": f"Bearer {self.get_azure_management_token()}", "Content-Type": "application/json"}
        url = f"{self.management_endpoint}/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Fabric/capacities/{capacityName}/suspend?api-version=2023-11-01"
        response = requests.post(url, headers=headers)
        return handle_response(response, Capacity)

    def resume_capacity(self, capacityName: str, subscriptionId: str, resourceGroupName: str):
        headers = {"Authorization": f"Bearer {self.get_azure_management_token()}", "Content-Type": "application/json"}
        url = f"{self.management_endpoint}/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Fabric/capacities/{capacityName}/resume?api-version=2023-11-01"
        response = requests.post(url, headers=headers)
        return handle_response(response, Capacity)

    def create_capacity(self, create_capacity_request: CreateCapacityRequest):
        self.validate_capacity_size(create_capacity_request.size)
        headers={"Authorization": f"Bearer {self.get_azure_management_token()}", "Content-Type": "application/json"}
        url = f"{self.management_endpoint}/{create_capacity_request.subscriptionId}/resourceGroups/{create_capacity_request.resourceGroupName}/providers/Microsoft.Fabric/capacities/{create_capacity_request.capacityName}?api-version=2023-11-01"
        body = {
            "properties": {
                "administration": {
                    "members": [create_capacity_request.admin]
                }
            },
            "sku": {
                "name": create_capacity_request.size,
                "tier": "Fabric"
            },
            "location": create_capacity_request.location
        }
        
        create_capacity_response = requests.put(url=url, data=json.dumps(body), headers=headers)
        
        if create_capacity_response.status_code > 299:
            raise Exception(f"Failed to create capacity: {create_capacity_response.content}")
        
        # Update capacity succeeded
        if create_capacity_response.status_code == 200:
            self.logger.info("Updating capacity...")
            updating_location = create_capacity_response.headers["Location"]
            updating_response = requests.get(updating_location, headers)
            
            self.logger.info(updating_response.status_code)
            self.logger.info(updating_response.content)
        
        # Creating capacity
        if create_capacity_response.status_code == 201:
            provisioning_location = create_capacity_response.headers["Location"]

            print(provisioning_location)
            provisioning_response = requests.get(provisioning_location, headers=headers)

            print(json.dumps(provisioning_response.status_code))
            
            # No response body
            if provisioning_response.status_code == 202:
                return
            
            print(json.dumps(provisioning_response.content, indent=2))
            
            provisioning_response_content = json.loads(provisioning_response.content)
            
            while provisioning_response_content["properties"]["provisioningState"] == "Provisioning":
                sleep(3)
                print("Capacity still provisioning...")
                provisioning_response = requests.get(provisioning_location, headers=headers)
                provisioning_response_content = json.loads(provisioning_response.content)
                print(json.dumps(provisioning_response_content, indent=2))
            
            print(f"Last provisioning state: {provisioning_response['properties']['provisioningState']}")

    def get_azure_management_token(self):
        if isinstance(self.token_provider, CertificateBasedAuthTokenProvider):
            return self.token_provider.get_azure_management_token()
        return self.token_provider.get_token()