from pydantic import BaseModel
from typing import Optional, Any

class EnrichmentAPIResponse(BaseModel):
    """
    Represents a response model for API calls.

    Attributes:
        data (Any):
            The data payload from the API response. 
        error_message (Optional[str]):
            If the API request fails, this field will contain a message describing the error.
        is_completed (bool):
            True if there is no error message, indicating the operation is completed successfully.
    """
    data: Optional[Any] = None
    error_message: Optional[str] = None
    
    @property
    def is_completed(self) -> bool:
        """
        Returns True if there is no error message, indicating the operation is completed successfully.

        Returns:
            bool: True if there is no error message, False otherwise.
        """
        return not self.error_message


    def to_dict(self) -> dict:
        """
        Converts the EnrichmentAPIResponse instance to a dictionary.

        Returns:
            dict: A dictionary representation of the EnrichmentAPIResponse instance.
        """
        return {
            "data": self.data,
            "error_message": self.error_message,
            "is_completed": self.is_completed
        }