# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------
import base64
import gzip
import io
from typing import Any, Dict, List
from PIL import Image
import numpy as np
import pydicom
import requests
from microsoft.fabric.hls.hds.ai_enrichments.core.base_classes.enrichment_model_client_base import EnrichmentModelClientBase
from microsoft.fabric.hls.hds.ai_enrichments.core.clients.models.enrichment_api_response import EnrichmentAPIResponse
from microsoft.fabric.hls.hds.ai_enrichments.core.errors.enrichment_value_error import EnrichmentValueError
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_constants import AIEnrichmentsConstants as EC


class MedImageClientOrchestrator(EnrichmentModelClientBase):
    """
    Orchestrates calls to MedImage-based models for image enrichment.
    """

    def __init__(
        self,
        api_endpoint: str,
        api_key: str,
        **kwargs
    ):
        """
        Initialize the orchestrator with service endpoint and credentials.

        Args:
            api_endpoint (str): The API endpoint URL.
            api_key (str): The authentication key.
            kwargs: Additional key-value attributes.
        """
        super().__init__(api_endpoint, api_key, **kwargs)

    def execute(self, file_contents: List[str]) -> List[EnrichmentAPIResponse]:
        """
        Run the enrichment process for the provided file paths.

        Args:
            file_contents (List[str]): List of file paths to be processed.

        Returns:
            List[EnrichmentAPIResponse]: List of enrichment API responses.
        """
        responses = []
        for file_content in file_contents:
            responses.append(self._process_file(file_content))
        return responses

    def _process_file(self, file_content: str) -> EnrichmentAPIResponse:
        """
        Process a single file and return the response.

        Args:
            file_path (str): Path to the file to be processed.

        Returns:
            EnrichmentAPIResponse: The response from the enrichment API.
        """
        try:
            file_content_data=gzip.decompress(base64.b64decode(file_content))
            encoded_data = MedImageClientOrchestrator.encode_dicom_image(file_content_data)
            payload = self._build_payload(encoded_data)
            result = MedImageClientOrchestrator.submit_request(
                api_endpoint=self.api_endpoint,
                headers=self.get_headers(),
                api_key=self.api_key,
                json=payload
            )
            return EnrichmentAPIResponse(data=result)
        except Exception as ex:
            return EnrichmentAPIResponse(error_message=str(ex))
    
    @staticmethod
    def encode_dicom_image(dicom_bytes: bytes) -> str:
        """
        Convert bytes data to a DICOM object, extract the pixel array, and encode it as a base64 PNG image.

        Args:
            dicom_bytes (bytes): The DICOM file in bytes.

        Returns:
            str: The base64 encoded PNG image.
        """
        try:
           
            # Convert bytes data to a DICOM object with force=True
            dicom_file = pydicom.dcmread(io.BytesIO(dicom_bytes), force=True)

            # Check if the DICOM file contains pixel data
            if not hasattr(dicom_file, "pixel_array"):
                    raise EnrichmentValueError(f"Error processing DICOM image: {e}-{dicom_bytes}")

            # Extract pixel array from DICOM object
            pixel_array = dicom_file.pixel_array
            
            # Rescale the pixel data to 8-bit
            image = (pixel_array / np.max(pixel_array) * 255).astype(np.uint8)

            # Convert the numpy array to a PIL Image
            pil_image = Image.fromarray(image)

            # Save the image to a bytes buffer
            with io.BytesIO() as buffer:
                pil_image.save(buffer, format="PNG")
                encoded_image = base64.b64encode(buffer.getvalue()).decode("utf-8") 
            return encoded_image    
        except Exception as e:
            raise EnrichmentValueError(f"Error processing DICOM image: {e}-{dicom_bytes}")
        
    @staticmethod
    def submit_request(api_endpoint: str, api_key: str, method: str = "POST",headers:Dict={},logger=None, **kwargs) -> Any:
        """
        The `submit_request` method executes an HTTP request to a specified API endpoin. It supports various HTTP methods (e.g., 'GET', 'POST') and includes authorization using an API key. The method also allows for additional keyword arguments to be passed for the request.

        Args:
            api_endpoint (str): The API endpoint URL.
            api_key (str): The API key for authorization.
            method (str): The HTTP method (default is 'POST').
            logger (Optional): Logger for logging errors.
            **kwargs: Additional keyword arguments for the request.

        Returns:
            Any: The response from the API.

        Raises:
            requests.RequestException: If the request fails.
        """
        try:
            response = requests.request(method, api_endpoint, headers=headers, timeout=EC.DEFAULT_REQUEST_TIMEOUT, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            if logger:
                logger.error(f"Request to {api_endpoint} failed: {e}")
            raise
        

    def _build_payload(self, encoded_data: str) -> Dict[str, Any]:
        """
        Build and return the JSON payload for the enrichment request.

        Args:
            encoded_data (str): The encoded image data.

        Returns:
            Dict[str, Any]: The JSON payload for the enrichment request.
        """

        return {
            "input_data": {
                "columns": ["image", "text"],
                "index": [0],
                "data": [[encoded_data, self.system_instructions or ""]]
            },
            "params": {}
        }

