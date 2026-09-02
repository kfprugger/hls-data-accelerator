# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------
import json
from urllib.parse import urlparse
from typing import List, Union
from pyspark.sql.functions import col, when, coalesce, lit
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_constants import AIEnrichmentsConstants as EC
from pyspark.sql import SparkSession
from pyspark.sql.column import Column
from pyspark.sql.types import StructType
from microsoft.fabric.hls.hds.utils.utils import Utils

class AIEnrichmentIngestionUtils:
    """
    A utility class for AIEnrichment ingestion-related operations.
    """
    
    @staticmethod
    def is_udf_registered(spark:SparkSession, udf_name: str) -> bool:
            """
            Check if UDF is registered in spark session.
            """
            return udf_name in [f.name for f in spark.catalog.listFunctions()]

    @staticmethod
    def get_schema_from_json_file(
        spark: SparkSession, schemas_path: str
    ) -> Union[StructType, None]:
        
        """
        Get the schema for the enrichment resource.
        """
        # Load the schema as a string
        try:
            schema_str = Utils.load_config_file(spark, schemas_path)
            schema_json = json.loads(schema_str)  # Parse JSON string
            schema = StructType.fromJson(schema_json)
            return schema
        except Exception as e:
            raise e

    @staticmethod
    def construct_failed_file_path(failed_folder_path: str, file_path: str, levels_to_retain: int) -> str:
        """
        Constructs the destination path for failed files by retaining a specified number of 
        levels from the original file path and prefixing the filename with 'failed_'.

        Args:
            failed_folder_path (str): Base folder path for failed files.
            file_path (str): Original file path.
            levels_to_retain (int): Number of levels to retain from the original file path.

        Returns:
            str: The constructed path for the failed file.
        """
        parsed_path = urlparse(file_path)
        path_components = parsed_path.path.strip("/").split("/")

        # Ensure the path has enough levels
        if len(path_components) < levels_to_retain:
            raise ValueError(
                f"File path '{file_path}' does not have the expected number of components."
            )

        relative_path = "/".join(path_components[-levels_to_retain:])
        file_name = path_components[-1]
        failed_file_name = f"failed_{file_name}"
        return f"{failed_folder_path}/{relative_path}".replace(file_name, failed_file_name)
    
    @staticmethod
    def get_silver_enrichment_table_fields(enrichment_type: str) -> List[Column]:
        """
        Get the combined list of common and specific fields based on the enrichment type.

        Args:
            enrichment_type (str): The type of enrichment.

        Returns:
            List[Column]: The combined list of common and specific fields.
        """

        def _get_common_fields() -> List[Column]:
            return [
                col(EC.ENRICHMENT_SILVER_UNIQUE_ID_COLUMN),
                col(EC.ENRICHMENT_SILVER_MODEL_NAME_COLUMN),
                col(EC.ENRICHMENT_SILVER_MODEL_VERSION_COLUMN),
                col(EC.ENRICHMENT_SILVER_PATIENT_ID_COLUMN),
                col(EC.ENRICHMENT_GENERATION_ID_COLUMN),
                col(EC.ENRICHMENT_DEFINITION_ID_COLUMN),
                col(EC.ENRICHMENT_SILVER_METADATA_COLUMN),
                col(EC.ENRICHMENT_CONTEXT_ID_COLUMN),
                col(EC.ENRICHMENT_SILVER_CONFIDENCE_SCORE_COLUMN),
            ]

        def _get_text_fields() -> List[Column]:
            return [
                col(EC.ENRICHMENT_PARSED_VALUE).alias(EC.ENRICHMENT_SILVER_TEXT_VALUE_COLUMN),
                col(EC.ENRICHMENT_PARSED_DOMAIN).alias(EC.ENRICHMENT_SILVER_TEXT_DOMAIN_COLUMN),
                col(EC.ENRICHMENT_PARSED_REASONING).alias(EC.ENRICHMENT_SILVER_TEXT_REASONING_COLUMN),
                col(EC.ENRICHMENT_PARSED_EVIDENCE).alias(EC.ENRICHMENT_SILVER_TEXT_EVIDENCE_COLUMN),
                col(EC.ENRICHMENT_PARSED_TERMINOLOGY).alias(EC.ENRICHMENT_SILVER_TEXT_TERMINOLOGY_COLUMN),
            ]

        def _get_object_fields() -> List[Column]:
            return [
                col(EC.ENRICHMENT_PARSED_VALUE).alias(EC.ENRICHMENT_SILVER_OBJECT_VALUE_COLUMN),
                col(EC.ENRICHMENT_PARSED_TYPE).alias(EC.ENRICHMENT_SILVER_OBJECT_TYPE_COLUMN),
                col(EC.ENRICHMENT_PARSED_REASONING).alias(EC.ENRICHMENT_SILVER_OBJECT_REASONING_COLUMN),
                col(EC.ENRICHMENT_PARSED_EVIDENCE).alias(EC.ENRICHMENT_SILVER_OBJECT_EVIDENCE_COLUMN),
                col(EC.ENRICHMENT_PARSED_DESCRIPTION).alias(EC.ENRICHMENT_SILVER_OBJECT_DESCRIPTION_COLUMN),
            ]

        def _get_embedding_fields() -> List[Column]:
            return [
                col(EC.ENRICHMENT_PARSED_VECTOR).alias(EC.ENRICHMENT_SILVER_EMBEDDING_VECTOR_COLUMN),
            ]

        def _get_seg2d_fields() -> List[Column]:
            return [
                col(EC.ENRICHMENT_PARSED_HEIGHT).alias(EC.ENRICHMENT_SILVER_SEGMENTATION_HEIGHT_COLUMN),
                col(EC.ENRICHMENT_PARSED_WIDTH).alias(EC.ENRICHMENT_SILVER_SEGMENTATION_WIDTH_COLUMN),
                col(EC.ENRICHMENT_PARSED_BACKGROUND).alias(EC.ENRICHMENT_SILVER_SEGMENTATION_BACKGROUND_COLUMN),
                col(EC.ENRICHMENT_PARSED_SEGMENTATION_MASK_METADATA).alias(EC.ENRICHMENT_SILVER_SEGMENTATION_METADATA_COLUMN),
                when(
                    col(EC.ENRICHMENT_PARSED_CLASS_LABEL_MASK).isNotNull(), lit("REF")
                ).otherwise(
                    coalesce(
                        col(EC.ENRICHMENT_PARSED_RLE_MASK),
                        col(EC.ENRICHMENT_PARSED_BOUNDING_BOX)
                    )
                ).alias(EC.ENRICHMENT_SILVER_SEGMENTATION_VALUE_COLUMN),
                when(
                    col(EC.ENRICHMENT_PARSED_CLASS_LABEL_MASK).isNotNull(),
                    col(EC.ENRICHMENT_BRONZE_FULL_FILE_PATH_COLUMN)
                ).otherwise(None).alias(EC.ENRICHMENT_SILVER_SEGMENTATION_FILE_REF_MASK_COLUMN),
                when(
                    col(EC.ENRICHMENT_PARSED_RLE_MASK).isNotNull(), EC.ENRICHMENT_SEGMENTATION_RLE_TYPE
                ).when(
                    col(EC.ENRICHMENT_PARSED_BOUNDING_BOX).isNotNull(),
                    EC.ENRICHMENT_SEGMENTATION_BOUNDING_BOX_TYPE
                ).when(
                    col(EC.ENRICHMENT_PARSED_CLASS_LABEL_MASK).isNotNull(),
                    EC.ENRICHMENT_SEGMENTATION_CLASS_LABEL_TYPE
                ).otherwise(None).alias(EC.ENRICHMENT_SILVER_SEGMENTATION_TYPE_COLUMN),
            ]

        def _get_seg3d_fields() -> List[Column]:
            return [
                col(EC.ENRICHMENT_PARSED_HEIGHT).alias(EC.ENRICHMENT_SILVER_SEGMENTATION_HEIGHT_COLUMN),
                col(EC.ENRICHMENT_PARSED_WIDTH).alias(EC.ENRICHMENT_SILVER_SEGMENTATION_WIDTH_COLUMN),
                col(EC.ENRICHMENT_PARSED_DEPTH).alias(EC.ENRICHMENT_SILVER_SEGMENTATION_DEPTH_COLUMN),
                col(EC.ENRICHMENT_PARSED_BACKGROUND).alias(EC.ENRICHMENT_SILVER_SEGMENTATION_BACKGROUND_COLUMN),
                col(EC.ENRICHMENT_PARSED_SEGMENTATION_MASK_METADATA).alias(EC.ENRICHMENT_SILVER_SEGMENTATION_METADATA_COLUMN),
                when(
                    col(EC.ENRICHMENT_PARSED_CLASS_LABEL_MASK).isNotNull(), lit("REF")
                ).otherwise(
                    coalesce(
                        col(EC.ENRICHMENT_PARSED_RLE_MASK),
                        lit(None)
                    )
                ).alias(EC.ENRICHMENT_SILVER_SEGMENTATION_VALUE_COLUMN),
                when(
                    col(EC.ENRICHMENT_PARSED_CLASS_LABEL_MASK).isNotNull(),
                    col(EC.ENRICHMENT_BRONZE_FULL_FILE_PATH_COLUMN)
                ).otherwise(None).alias(EC.ENRICHMENT_SILVER_SEGMENTATION_FILE_REF_MASK_COLUMN),
                when(
                    col(EC.ENRICHMENT_PARSED_RLE_MASK).isNotNull(), EC.ENRICHMENT_SEGMENTATION_RLE_TYPE
                ).when(
                    col(EC.ENRICHMENT_PARSED_CLASS_LABEL_MASK).isNotNull(),
                    EC.ENRICHMENT_SEGMENTATION_CLASS_LABEL_TYPE
                ).otherwise(None).alias(EC.ENRICHMENT_SILVER_SEGMENTATION_TYPE_COLUMN),
            ]

        # Main logic
        common_fields = _get_common_fields()
        enrichment_type_fields = []

        if enrichment_type == EC.ENRICHMENT_TYPE_TEXT:
            enrichment_type_fields = _get_text_fields()
        elif enrichment_type == EC.ENRICHMENT_TYPE_OBJECT:
            enrichment_type_fields = _get_object_fields()
        elif enrichment_type == EC.ENRICHMENT_TYPE_EMBEDDING:
            enrichment_type_fields = _get_embedding_fields()
        elif enrichment_type == EC.ENRICHMENT_TYPE_SEG2D:
            enrichment_type_fields = _get_seg2d_fields()
        elif enrichment_type == EC.ENRICHMENT_TYPE_SEG3D:
            enrichment_type_fields = _get_seg3d_fields()

        return common_fields + enrichment_type_fields
