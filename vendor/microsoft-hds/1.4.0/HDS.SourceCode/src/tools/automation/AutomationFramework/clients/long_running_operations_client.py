from logging import Logger
import requests
from utils.token_provider import TokenProvider
from time import sleep

class LongRunningOperationsClient:

    def __init__(self, token_provider: TokenProvider, env="msit", logger: Logger = None):
        self.token_provider = token_provider
        self.logger = logger
        self.endpoint_pattern = f"https://{env}api.fabric.microsoft.com/v1/operations/{{}}"

    def poll_operation(self, operation_id, interval_in_seconds = 3):
        
        operation_state = self.get_long_running_operations_state(operation_id)
        
        first_operation_poll = True
        operation_status = str(operation_state["status"]).lower()
        
        operation_finished = False
        while not operation_finished:
            
            if operation_status == "running":
                self.logger.info("Operation is running, polling again in 3 seconds...")
                sleep(interval_in_seconds)
                operation_state = self.get_long_running_operations_state(operation_id)
                operation_status = str(operation_state["status"]).lower()
            
            elif operation_status == "notstarted" and first_operation_poll:
                self.logger.info("Operation not started, polling again in 3 seconds...")
                sleep(interval_in_seconds)
                
            else:
                operation_finished = True
                
            first_operation_poll = False

        if operation_status == "succeeded":
            operation_result = self.get_long_running_operation_result(operation_id)
            self.logger.info("Operation completed successfully.")
            return operation_result
        else:
            self.logger.info(f"Operation failed with id {operation_id}")
            return None

    def get_long_running_operation_result(self, operation_id):
        base_url = self.endpoint_pattern.format(operation_id)+ "/result"
        response = requests.get(base_url, headers=self.get_headers())
        return response.json()

    def get_long_running_operations_state(self, operation_id):
        base_url = self.endpoint_pattern.format(operation_id)
        response = requests.get(base_url, headers=self.get_headers())
        return response.json()
    
    def get_headers(self):
        token = self.token_provider.get_token()
        return { "Authorization": f"Bearer {token}", "Content-Type": "application/json" }