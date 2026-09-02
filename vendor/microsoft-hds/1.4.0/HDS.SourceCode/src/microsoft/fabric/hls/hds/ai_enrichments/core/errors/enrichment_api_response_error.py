from microsoft.fabric.hls.hds.ai_enrichments.core.errors.enrichment_error_base import EnrichmentErrorBase


class EnrichmentAPIResponseError(EnrichmentErrorBase):
    """
    Represents errors encountered during the enrichment api response process.

    Attributes:
        message (str): The error message.
        status_code (int, optional): The HTTP-like status code.
        retry_after (int, optional): Time (in seconds) after which a retry can be attempted.
    """

    def __init__(self, message: str, status_code: int = None, retry_after: int = None):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after
