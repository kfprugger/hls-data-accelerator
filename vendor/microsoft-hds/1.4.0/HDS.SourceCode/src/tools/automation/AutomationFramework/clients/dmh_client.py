import json
from typing import List
import requests

from models.healthcare_data_solution_item import HealthcareDataSolutionItem
from utils.token_provider import TokenProvider
from .client_utils import handle_list_response, handle_response
from logging import Logger

class DmhClient:

    def __init__(self, token_provider: TokenProvider, env="msit", logger: Logger = None):
        self.token_provider = token_provider
        self.endpoint = f"https://{env}api.fabric.microsoft.com/v1/workspaces/{{}}/items"
        self.logger = logger

    def create_healthcare_data_solution(self, workspace_id: str, solution_display_name: str) -> HealthcareDataSolutionItem:
        base_url = self.endpoint.format(workspace_id)

        data = {
            'displayName': solution_display_name,
            'type': 'Healthcaredatasolution'
        }
        response = requests.post(base_url, headers=self.get_headers(), data=json.dumps(data))

        return handle_response(response, HealthcareDataSolutionItem)

    def get_healthcare_data_solution(self, workspace_id: str, solution_id: str) -> HealthcareDataSolutionItem:
        base_url = self.endpoint.format(workspace_id) + "/" + solution_id
        response = requests.get(base_url, headers=self.get_headers())
        return handle_response(response, HealthcareDataSolutionItem)

    def get_healthcare_data_solutions(self, workspace_id) -> List[HealthcareDataSolutionItem]:
        base_url = self.endpoint.format(workspace_id) + "?type=Healthcaredatasolution"
        response = requests.get(base_url, headers=self.get_headers())
        return handle_list_response(response, HealthcareDataSolutionItem)

    def get_headers(self):
        token = self.token_provider.get_token()
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}