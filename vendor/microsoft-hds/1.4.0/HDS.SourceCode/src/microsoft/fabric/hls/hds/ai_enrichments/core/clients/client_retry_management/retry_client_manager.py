# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------
from typing import Callable, Optional, Dict, Any
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential
)
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_constants import AIEnrichmentsConstants as EC
from microsoft.fabric.hls.hds.ai_enrichments.core.clients.client_retry_management.client_manager_utils import ClientManagerUtils as CMUtils


class RetryClientManager:
    _default_retry_params: Dict[str, Any] = {
        "total_retries": EC.DEFAULT_TOTAL_RETRIES,
        "retry_delay_multiplier": EC.DEFAULT_DELAY_MULTIPLIER,
        "min_backoff": EC.DEFAULT_MIN_BACKOFF,
        "max_backoff": EC.DEFAULT_MAX_BACKOFF,
        "retry_on_status_codes": EC.DEFAULT_RETRY_ON_STATUS_CODES,
    }

    def __init__(self, client: Any, retry_params: Optional[Dict[str, Any]] = None):
        self.client = client
        self.retry_params = {**self._default_retry_params, **(retry_params or {})}

    def get_client_executor(self, method_name: str="execute") -> Callable[..., Any]:
        """
        Executes a client method with retry logic.

        Args:
            method_name (str): The name of the method to be executed on the client.

        Returns:
            Callable[..., Any]: A callable that executes the specified method with retry logic.
        """
        if not isinstance(method_name, str):
            raise TypeError(f"Method name must be a string, got {type(method_name).__name__}")
        method = getattr(self.client, method_name, None)
        if method is None:
            raise AttributeError(f"Method {method_name} does not exist on the client.")

        @self._retry_decorator()
        def client_execution_method(*args, **kwargs) -> Any:
            return method(*args, **kwargs)

        try:
            return client_execution_method
        except Exception as e:
            raise



    def _retry_decorator(self) -> Callable[..., Any]:
        return retry(
            retry=retry_if_exception(
                lambda exc: CMUtils.should_retry_on_exception(
                    exc, self.retry_params.get("retry_on_status_codes")
                )
            ),
            wait=wait_random_exponential(
                multiplier=self.retry_params.get("retry_delay_multiplier", EC.DEFAULT_DELAY_MULTIPLIER),
                min=self.retry_params.get("min_backoff", EC.DEFAULT_MIN_BACKOFF),
                max=self.retry_params.get("max_backoff", EC.DEFAULT_MAX_BACKOFF)
            ),
            stop=stop_after_attempt(
                self.retry_params.get("total_retries", EC.DEFAULT_TOTAL_RETRIES)
            )
        )