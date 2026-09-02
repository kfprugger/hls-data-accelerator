# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------
import base64
import hashlib
import json
import re
import uuid
import zlib
import pydicom
import numpy as np
import uuid
from PIL import Image
import io
import requests
from typing import Any, Dict, List
from microsoft.fabric.hls.hds.ai_enrichments.core.errors.enrichment_value_error import EnrichmentValueError
from microsoft.fabric.hls.hds.ai_enrichments.core.errors.execution_service_error import ExecutionServiceError
from microsoft.fabric.hls.hds.ai_enrichments.core.errors.model_configuration_error import ModelConfigurationError
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.metadata.enrichment_view import EnrichmentView
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.metadata.enrichment_view_definition import EnrichmentViewDefinition
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_context import EnrichmentContext
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_input import EnrichmentInput
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_constants import AIEnrichmentsConstants as EC
from pyspark.sql import SparkSession

class AIEnrichmentsUtils:
    @staticmethod
    def validate_views_in_sql_expression(sql_expression: str, n_views: int) -> bool:
        """
        Validate that the given SQL expression contains the specified number of views.

        Args:
            sql_expression (str): The SQL expression to validate.
            n_views (int): The number of views to check for in the SQL expression.

        Returns:
            bool: True if all views are present in the SQL expression, False otherwise.
        """
        sql_expression = sql_expression.lower()
        return all(f"view{i+1}" in sql_expression for i in range(n_views))
    
    @staticmethod
    def replace_materialized_view_names(spark: SparkSession,sql_expression: str, materialized_views_names: Dict[str, str]) -> str:
        """
        Replace placeholders for materialized view names in the SQL expression with actual names.

        Args:
            sql_expression (str): The SQL expression containing placeholders.
            materialized_views_names (Dict[str, str]): A dictionary where keys are placeholders and values are actual materialized view names.

        Returns:
            str: The SQL expression with placeholders replaced by actual materialized view names.
        """
        for i, (table_path, lake_house_name) in enumerate(materialized_views_names.items(), start=1):
            pattern = re.compile(re.escape(f"view{i}"), re.IGNORECASE)
            if lake_house_name:
               # Table referencing from lakehouse 
               sql_expression = pattern.sub(f"{lake_house_name}.{table_path}", sql_expression)
            else:
               #Materialized as files in lakehouse 
               materialized_view_table = spark.read.parquet(table_path)
               temp_materialized_view_table_name = f"{EC.ENRICHMENT_MATERIALIZED_FILE_PREFIX}{uuid.uuid4().hex}"
               materialized_view_table.createOrReplaceTempView(temp_materialized_view_table_name)
        return sql_expression
    
    @staticmethod
    def create_context_string(model_configuration: dict, enrichment_input: EnrichmentInput) -> str:
        """
        Generate a context string based on the provided model configuration and enrichment input.

        Args:
            model_configuration (dict): The configuration of the model used for enrichment.
            enrichment_input (EnrichmentInput): The input data for the enrichment process.

        Returns:
            str: A JSON string representing the combined model configuration and enrichment input.
        """
        combined_data = {
            "model_configuration": model_configuration,
            "enrichment_input": enrichment_input.to_dict()
        }
        return json.dumps(combined_data, separators=(',', ':'))
    
    @staticmethod
    def extract_sql_query(view: EnrichmentView, view_definition: EnrichmentViewDefinition) -> str:
        """
        Extract the SQL query from the view definition.

        Args:
            view (EnrichmentView): The enrichment view object.
            view_definition (EnrichmentViewDefinition): The definition of the enrichment view.

        Returns:
            str: The extracted SQL query.

        Raises:
            ExecutionServiceError: If the query type is not 'sql' or if the SQL query is not found.
        """
        query_expression = view_definition.expression
        query_type = query_expression.type
        if query_type != 'sql':
            raise ExecutionServiceError(EC.ENRICHMENT_INVALID_QUERY_TYPE.format(enrichment_view_info_id=view.id))
        sql_query = query_expression.query
        if not sql_query:
            raise ExecutionServiceError(EC.ENRICHMENT_SQL_QUERY_NOT_FOUND.format(enrichment_view_info_id=view.id))
        return sql_query
    
    @staticmethod
    def validate_input_mapping(input_mapping, enrichment_id):
        """
        Validate the input mapping for enrichment.

        Args:
            input_mapping: The input mapping to validate.
            enrichment_id: The ID of the enrichment.

        Raises:
            EnrichmentValueError: If the input mapping is invalid.
        """
        if not input_mapping:
            raise EnrichmentValueError(EC.ENRICHMENT_INPUT_MAPPING_NOT_FOUND.format(enrichment_id=enrichment_id))

        if not input_mapping.patient_id:
            raise EnrichmentValueError(EC.ENRICHMENT_METADATA_PATIENT_ID_NOT_FOUND)

        if not input_mapping.text_resource_references and not input_mapping.image_resource_references:
            raise EnrichmentValueError(EC.ENRICHMENT_RESOURCE_REFERENCES_NOT_FOUND.format(enrichment_id=enrichment_id))
        
    @staticmethod      
    def serialize_json_data(data: Any) -> bytes:
        """
        Serialize JSON data to bytes.

        Args:
            data (Any): The data to serialize.

        Returns:
            bytes: The serialized data.
        """
        json_string = json.dumps(data)
        return json_string.encode("utf-8")
    
    @staticmethod 
    def serialize_text_data(data: Any) -> bytes:
        """
        Serialize text data to bytes.

        Args:
            data (Any): The data to serialize.

        Returns:
            bytes: The serialized data.
        """
        return data.encode("utf-8")
    
    @staticmethod
    def deserialize_data(value: bytes) -> str:
        """
        Deserialize bytes to a string.

        Args:
            value (bytes): The data to deserialize.

        Returns:
            str: The deserialized data.
        """
        return value.decode("utf-8")
        
    @staticmethod
    def get_hash_id(data: str) -> str:
        """
        Generate a hash ID for the given data.

        Args:
            data (str): The data to hash.

        Returns:
            str: The hash ID or empty string if data is None.
        """
        
        hash_value = hashlib.sha256(data.encode('utf-8')).hexdigest()
        return hash_value[:64]
    
    @staticmethod
    def get_base64_encoded_string(data: str) -> str:
        """
        Encode the given data to a base64 string.

        Args:
            data (str): The data to encode.

        Returns:
            str: The base64 encoded string.
        """
        return base64.b64encode(zlib.compress(data.encode('utf-8'))).decode("utf-8")

    @staticmethod
    def validate_model_config(model_config: dict):
        """
        Validates the model configuration.

        Args:
            model_config (dict): Configuration for the Model.

        Raises:
            ModelConfigurationError: If the model configuration is invalid.
        """
        if model_config is None or not model_config.get("api_endpoint") or not model_config.get("api_key"):
            raise ModelConfigurationError(EC.ENRICHMENT_MODEL_CONFIGURATION_INVALID)
    
    

    @staticmethod    
    def get_content_from_file_references(
        document_inputs: List[EnrichmentContext],
    ) -> List[str]:
        """
        Extracts file content from document inputs.

        Args:
            document_inputs (List[EnrichmentContext]): List of context inputs.

        Returns:
            List[str]: Collection of extracted file content.
        """
        # Collect content from each reference within each document context
        return [
            file.file_content
            for enrichment_context in document_inputs
            for file in enrichment_context.enrichment_input.image_file_references + enrichment_context.enrichment_input.text_file_references
        ]  
        
        
    @staticmethod
    def format_output_type_for_output_path(output_type: str) -> str:
        """
        Formats the output type for the enrichment results. This will be used in the file path.

        Args:
            output_type (str): The output type to format.

        Returns:
            str: The formatted output type.
        """
        formatted_output_type = output_type.capitalize()
        if formatted_output_type in ["Segmentation2d", "Segmentation3d"]:
            formatted_output_type = formatted_output_type[:-1] + formatted_output_type[-1].upper()
        return formatted_output_type
    