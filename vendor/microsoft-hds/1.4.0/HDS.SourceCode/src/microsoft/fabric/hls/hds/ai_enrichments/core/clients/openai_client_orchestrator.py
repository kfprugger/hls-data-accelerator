# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------

import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, List, Type, TypeVar
import openai
from pydantic import BaseModel
from microsoft.fabric.hls.hds.ai_enrichments.core.base_classes.enrichment_model_client_base import EnrichmentModelClientBase
from microsoft.fabric.hls.hds.ai_enrichments.core.clients.models.enrichment_api_response import EnrichmentAPIResponse
from microsoft.fabric.hls.hds.ai_enrichments.core.clients.openai_client.utils.openai_client_utils import OpenAIClientUtils as OpenAIUtils
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_logging_constants import AIEnrichmentsLoggingConstants as ELC
from microsoft.fabric.hls.hds.ai_enrichments.core.errors.enrichment_value_error import EnrichmentValueError
from microsoft.fabric.hls.hds.ai_enrichments.core.errors.model_configuration_error import ModelConfigurationError
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_constants import AIEnrichmentsConstants as EC
from microsoft.fabric.hls.hds.ai_enrichments.core.clients.openai_client.openai_constants import OpenAIConstants
from microsoft.fabric.hls.hds.ai_enrichments.core.clients.openai_client.models.openai_model_response import OpenAIModelResponse
from microsoft.fabric.hls.hds.ai_enrichments.core.clients.openai_client.models.openai_model_settings import OpenAIModelSettings
from microsoft.fabric.hls.hds.ai_enrichments.core.clients.openai_client.models.openai_enrichment_output import OpenAIEnrichmentOutput

T = TypeVar("T", bound=BaseModel)


class OpenAIClientOrchestrator(EnrichmentModelClientBase):
    """
    Handles interactions with the OpenAI API, including chat completion and
    utilization of assistants/threads for conversational operations.
    """

    def __init__(  
        self,
        api_endpoint: str,
        api_key: str,
        **kwargs
    ):
        """
        Initializes the OpenAIClientOrchestrator with configuration settings.

        Args:
            api_endpoint (str): The API endpoint URL.
            api_key (str): The authentication key.
            **kwargs: Additional attributes (e.g., open_ai_conn_config, openai_settings, etc.).
        """
        super().__init__(api_endpoint, api_key, **kwargs)
        self.openai_settings = kwargs.get("openai_settings") or OpenAIModelSettings()
        open_ai_conn_config = kwargs.get("open_ai_conn_config")
        system_message = kwargs.get("system_message")
        examples = kwargs.get("examples")
        self._initialize_chat_completion_params(
            open_ai_conn_config.model_name, open_ai_conn_config.open_ai_config_options
        )
        self.open_ai_conn_config = open_ai_conn_config
        self.openai_conn = openai.AzureOpenAI(
            azure_endpoint=open_ai_conn_config.azure_endpoint,
            api_key=open_ai_conn_config.api_key,
            api_version=open_ai_conn_config.api_version,
        )
        if not self._validate_api_key():
            raise ModelConfigurationError(ELC.OPENAI_ENRICHMENT_INVALID_API_KEY)
        self.system_instructions = OpenAIUtils.create_system_instructions(
            system_message, examples
        )

    def execute(self, model_inputs: List[Any], **kwargs) -> List[EnrichmentAPIResponse]:
        """
        Executes OpenAI completions for a list of user queries in parallel.

        Args:
            model_inputs (List[Any]): A list of query strings or data objects.
            **kwargs: Additional parameters if needed.

        Returns:
            List[EnrichmentAPIResponse]: Processed OpenAI responses.
        """

        def call_completion(
            user_query: str,
            response_model: any
        ) -> EnrichmentAPIResponse:
            """
            Calls the completion method for each query and handles exceptions.

            Args:
                user_query (str): The user query or text.
                response_model (OpenAIEnrichmentOutput): Model for validating the response.

            Returns:
                EnrichmentAPIResponse: Successful response or error details.
            """
            try:
                if not user_query or not response_model:
                    raise EnrichmentValueError(ELC.AI_ENRICHMENT_CLIENT_EXECUTION_ERROR.format(error=ELC.OPENAI_ENRICHMENT_MODEL_CONFIG_ERROR))
                response = self.parse_completion_json(
                    user_query=user_query,
                    response_model=response_model
                )
                return EnrichmentAPIResponse(data=response)
            except Exception as e:
                print("Error in OpenAI completion:", e)
                return EnrichmentAPIResponse(error_message=str(e))

        responses = []

        with ThreadPoolExecutor(
            max_workers=EC.DEFAULT_AI_ENRICHMENT_EXECUTION_THREADS
        ) as executor:
            futures = [
                executor.submit(
                    call_completion,
                    user_query=text,
                    response_model=OpenAIEnrichmentOutput,
                )
                for text in model_inputs
            ]
            for future in futures:
                response = future.result()
                responses.append(response)
        return responses

    def validate_openai_connection_config(self) -> bool:
        """
        Validates the OpenAI connection configuration.

        Returns:
            bool: True if valid, False otherwise.
        """
        return OpenAIUtils.validate_open_ai_config(self.open_ai_conn_config)

    def _validate_api_key(self) -> bool:
        """
        Confirms validity of the API key by listing assistants.

        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            self.list_assistants()
        except Exception as e:
            return False
        return True

    def parse_completion_json(
        self,
        user_query: str,
        response_model: Type[T]
    ) -> OpenAIModelResponse:
        """
        Generates and validates OpenAI completions.

        Args:
            user_query (str): The user's prompt.
            response_model (Type[T]): The Pydantic model for response validation.

        Returns:
            OpenAIModelResponse: Parsed response conforming to the specified model.
        """
        self.chat_completion_params["messages"] = OpenAIUtils.create_messages(
            user_query, list(self.system_instructions)
        )
        self.chat_completion_params["response_format"] = response_model
        parsed_chat_completion = self.openai_conn.beta.chat.completions.parse(
            **self.chat_completion_params
        )
        total_tokens = parsed_chat_completion.usage.total_tokens
        print(
            ELC.OPENAI_DATA_ENRICHMENT_TOKENS_USAGE_INFO_MSG.format(
                token_count=total_tokens
            )
        )
        completion_result = OpenAIUtils.process_completion_message(
            parsed_chat_completion
        )
        formatted_json = json.loads(completion_result)
        return formatted_json

    def list_assistants(self, order: str = "desc", limit: int = 20) -> List:
        """
        Retrieves existing assistants from the OpenAI service.

        Args:
            order (str, optional): Order in which to list. Defaults to "desc".
            limit (int, optional): Maximum number of items. Defaults to 20.

        Returns:
            List: Collection of assistants.
        """
        assistants = self.openai_conn.beta.assistants.list(
            order=order,
            limit=limit,
        )
        return assistants.data

    def create_new_assistant(
        self,
        assistant_name: str,
        system_instructions: str,
        model_name: str
    ):
        """
        Creates a new assistant with given attributes.

        Args:
            assistant_name (str): Desired name of the assistant.
            system_instructions (str): Instructions for system prompts.
            model_name (str): Model to use for processing.

        Returns:
            The newly created assistant or raises an exception on error.
        """
        try:
            assistant = self.openai_conn.beta.assistants.create(
                instructions=system_instructions,
                model=model_name,
                tools=[{"type": OpenAIConstants.ASSISTANT_TYPE}],
                name=assistant_name,
            )
            return assistant
        except Exception as ex:
            raise ex
   

    def _initialize_chat_completion_params(
        self,
        model_name: str,
        openai_config_options: dict
    ):
        """
        Sets up initial parameters for chat completions.

        Args:
            model_name (str): The chosen OpenAI model.
            openai_config_options (dict): Additional config parameters.
        """
        openai_config_attributes = openai_config_options or {}
        openai_settings = {**vars(self.openai_settings), **openai_config_attributes}
        self.chat_completion_params = {
            "model": model_name,
            "temperature": openai_settings.get("temperature"),
            "top_p": openai_settings.get("top_p"),
            "frequency_penalty": openai_settings.get("frequency_penalty"),
            "presence_penalty": openai_settings.get("presence_penalty"),
            "stop": openai_settings.get("stop"),
            "response_format": openai_settings.get("response_format"),
        }

    def _extract_error_info(self, error_text: str):
        """
        Extracts submission failure information from error text.

        Args:
            error_text (str): Text description of the error.

        Returns:
            Tuple (str, int): Error code (if present) and retry interval in seconds.
        """
        try:
            error_code_pattern = r"Error code: (\d+)"
            retry_seconds_pattern = r"retry after (\d+) seconds"

            def _search_pattern(pattern):
                match = re.search(pattern, error_text)
                return match.group(1) if match else None

            error_code_match = _search_pattern(error_code_pattern)
            retry_seconds_match = _search_pattern(retry_seconds_pattern)
            retry_seconds = int(retry_seconds_match) if retry_seconds_match else 0
            return error_code_match, retry_seconds
        except Exception as e:
            print(f"Error extracting error info: {e}")
            return None, None
