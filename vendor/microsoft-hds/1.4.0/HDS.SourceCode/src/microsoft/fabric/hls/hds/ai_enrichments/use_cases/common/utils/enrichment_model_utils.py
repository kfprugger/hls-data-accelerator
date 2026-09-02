 # -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------
import base64
from collections import namedtuple
import json
from typing import List
import numpy as np
from microsoft.fabric.hls.hds.ai_enrichments.core.clients.client_retry_management.retry_client_manager import RetryClientManager
from microsoft.fabric.hls.hds.ai_enrichments.core.clients.med_image_client_orchestrator import MedImageClientOrchestrator
from microsoft.fabric.hls.hds.ai_enrichments.core.clients.models.enrichment_api_response import EnrichmentAPIResponse
from microsoft.fabric.hls.hds.ai_enrichments.core.clients.openai_client.models.openai_client_settings import OpenAIClientSettings
from microsoft.fabric.hls.hds.ai_enrichments.core.clients.openai_client_orchestrator import OpenAIClientOrchestrator
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_context import EnrichmentContext
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_response import EnrichmentResponse


ImageAnalysisData = namedtuple('ImageAnalysisData', ['metadata', 'rle', 'height', 'width'])

class EnrichmentModelUtils:
      

    def initialize_med_image_client(model_config: dict) -> None:
        """
        Initializes the MedImage client.

        Args:
            model_config (dict): Configuration for the MedImageInsights model.
        """
        api_endpoint = model_config.get('api_endpoint',None)
        api_key = model_config.get('api_key',None)
        system_instructions = model_config.get('system_instructions',None)
        
        med_image_client = MedImageClientOrchestrator(api_endpoint=api_endpoint,api_key=api_key,
                                          system_instructions=system_instructions)
        
        return med_image_client
    
    
    def extract_content_from_documents(document_inputs: List[EnrichmentContext]) -> List[str]:
        """
        Extracts the file content from each document's references.
        """
        return [
            image_file.content
            for enrichment_context in document_inputs
            for image_file in enrichment_context.enrichment_input.image_file_references
        ]
        
        
    def analyze_images(client_manager:RetryClientManager, file_path_list: List[str]) -> List[dict]:
        """
        Calls the configured MedImageInsight model to process images and returns
        the model responses.
        
        Args:
        file_path_list (List[str]): A list of image file paths to be processed by the model.

        Returns:
            List[dict]: A list of dictionaries containing the model responses for each image.
        """       
        results = []

        execute_analyze = client_manager.execute_client()
        
        for file_path in file_path_list:
            results.append(execute_analyze(file_path=file_path))

        return results
    
    def format_analysis_results(
        enrichment_generation_id: str,
        document_inputs: List[EnrichmentContext],
        results: List[EnrichmentAPIResponse]
    ) -> List[EnrichmentResponse]:
        """
        Converts raw model responses into EnrichmentResponse objects and
        saves them if required.
        """
        formatted_responses = []
        if  len(document_inputs) == len(results):
            for i, result in enumerate(results):
                        response_data=result.data
                        enrichment_response = EnrichmentResponse(
                            id=document_inputs[i].enrichment_input.image_file_references[0].id,
                            content=response_data
                        )
                        formatted_responses.append(enrichment_response)   
        return formatted_responses
    
    
    def mask_to_rle(flattened_mask):
        """
        Convert a flattened mask to Run-Length Encoding (RLE).
        
        Args:
            flattened_mask (list or numpy array): Flattened binary mask (1s and 0s).
        
        Returns:
            list: RLE encoded mask.
        """
        rle = []
        try:
            last_val = 0
            run_start = -1

            for i, val in enumerate(flattened_mask):
                if val == 1 and last_val == 0:
                    run_start = i
                elif val == 0 and last_val == 1:
                    rle.extend([run_start, i - run_start])
                last_val = val

            if last_val == 1:
                rle.extend([run_start, len(flattened_mask) - run_start])
        except Exception as e:
           raise print(f"Error in mask_to_rle: {e}") 
        return rle
        

    def retrieve_image_analysis_data(entity: dict) -> List[ImageAnalysisData] | None:
        """
        Retrieve image analysis data from the given entity.

        Args:
            entity (dict): The entity containing image features and metadata.

        Returns:
            ImageAnalysisData | None: The image analysis data or None if data is missing.
        """
        image_features_metadata = json.loads(entity.get("image_features", "{}"))
        shape = image_features_metadata.get("shape", [])
        dtype = image_features_metadata.get("dtype", "float32")
        base64_data = image_features_metadata.get("data", "")
        text_features = entity.get("text_features", [])
        
        if not (shape and base64_data):
            return None
      
        height, width = (shape[1], shape[2]) if len(shape) > 2 else (0, 0)
        shaped_array = np.frombuffer(base64.b64decode(base64_data), dtype=dtype).reshape(shape)
        image_analysis_data = []
        for i,mask in enumerate(shaped_array):
            metadata = {
                "text_feature": text_features[i]
            }
            rle=EnrichmentModelUtils.mask_to_rle(mask.flatten())
            image_analysis_data.append(ImageAnalysisData(metadata=metadata, rle=rle, height=height, width=width))
        
        return image_analysis_data
    
    
    @staticmethod
    def get_med_image_client(model_config: dict, 
    ) -> MedImageClientOrchestrator:
        """
        Initializes the MedImage client with the provided configuration.

        Args:
            spark (SparkSession): Spark session instance.
            model_config (dict): Configuration for the model (endpoint, key, etc.).
        """
        # Retrieve settings from model_config
        api_endpoint = model_config.get("api_endpoint", None)
        api_key = model_config.get("api_key", None)
        system_instructions = model_config.get("system_instructions", None)

        # Instantiate the MedImageClientOrchestrator with provided settings
        med_image_client = MedImageClientOrchestrator(
            api_endpoint=api_endpoint,
            api_key=api_key,
            system_instructions=system_instructions
        )
        return med_image_client
    
   
      
    @staticmethod
    def get_conversational_client(model_config: dict) -> OpenAIClientOrchestrator:
        """
        Create and return an OpenAI client orchestrator for conversational use.
        """
        openai_config = OpenAIClientSettings(
            azure_endpoint=model_config.get("api_endpoint"),
            api_key=model_config.get("api_key"),
            api_version=model_config.get("version"),
            model_name=model_config.get("name"),
        )

        return OpenAIClientOrchestrator(
            api_endpoint=model_config.get("api_endpoint"),
            api_key=model_config.get("api_key"),
            open_ai_conn_config=openai_config,
            system_message=model_config.get("system_message"),
            examples=model_config.get("examples")
        ) 


