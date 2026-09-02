# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------
from typing import List, Optional
from requests.exceptions import ConnectionError, HTTPError, Timeout
from microsoft.fabric.hls.hds.ai_enrichments.core.errors.enrichment_api_response_error import EnrichmentAPIResponseError

class ClientManagerUtils:
    @staticmethod
    def should_retry_on_exception(ex: Exception, retry_on_status_codes: Optional[List[int]] = None) -> bool:
        """
        Determine if an exception should trigger a retry.

        Args:
            ex (Exception): The exception to evaluate.
            retry_on_status_codes (Optional[List[int]]): List of HTTP status codes that should trigger a retry.

        Returns:
            bool: True if the exception should trigger a retry, False otherwise.
        """
        if isinstance(ex, (ConnectionError, Timeout,EnrichmentAPIResponseError)):
            return True
        if isinstance(ex, HTTPError) and ex.response is not None:
            status_code = ex.response.status_code
            return (
                (retry_on_status_codes and status_code in retry_on_status_codes) or
                500 <= status_code < 600 or
                status_code == 429
            )
        return False