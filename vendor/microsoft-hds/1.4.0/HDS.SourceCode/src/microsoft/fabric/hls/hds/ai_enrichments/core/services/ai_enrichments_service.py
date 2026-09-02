# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# -------------------------------------------------------------------------
from typing import Any, Dict, Literal, Type, Optional
from pyspark.sql import SparkSession

from microsoft.fabric.hls.hds.ai_enrichments.core.errors.enrichment_service_error import EnrichmentServiceError
from microsoft.fabric.hls.hds.ai_enrichments.core.services.ai_enrichments_execution_service import AIEnrichmentsExecutionService
from microsoft.fabric.hls.hds.ai_enrichments.core.services.ai_enrichments_metadata_service import AIEnrichmentsMetaDataService
from microsoft.fabric.hls.hds.ai_enrichments.core.base_classes.enrichment_model_processor_base import EnrichmentModelProcessorBase
from microsoft.fabric.hls.hds.ai_enrichments.core.base_classes.enrichment_transformer_base import EnrichmentTransformerBase
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.utils.logging_helper import LoggingHelper
from microsoft.fabric.hls.hds.utils.parameter_service import ParameterService
from microsoft.fabric.hls.hds.utils.utils import Utils
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_logging_constants import AIEnrichmentsLoggingConstants as LC
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_constants import (
    AIEnrichmentsConstants as EC,
)


class AIEnrichmentsService:
    """
    Orchestrates the definition, creation, and execution of enrichment processes.

    This service is responsible for initializing and managing the various components
    required for AI enrichment, including parameter service, metadata service, and
    execution service. It ensures that the enrichment processes are defined, created,
    and executed properly.
    """

    def __init__(
        self,
        spark: SparkSession,
        workspace_name: str,
        solution_name: str,
        admin_lakehouse_name: str,
        enrichment_model_processor: Type[EnrichmentModelProcessorBase],
        enrichment_transformer: Type[EnrichmentTransformerBase],
        partition_config: dict =EC.ENRICHMENT_PARTITION_CONFIG_DEFAULT,
        inline_params: Optional[Dict[str, Any]] = None,
        output_format:Literal["json","ndjson"] = "ndjson",
        one_lake_endpoint: str = GC.DEFAULT_ONE_LAKE_ENDPOINT,
        mssparkutils_client: Optional[MSSparkUtilsClientBase] = None
    ) -> None:
        """
        Initializes the AIEnrichmentsService with the necessary components.

        Args:
            spark (SparkSession): The Spark session to use for data processing.
            workspace_name (str): The name of the workspace.
            solution_name (str): The name of the solution.
            admin_lakehouse_name (str): The name of the admin lakehouse.
            enrichment_model_processor (Type[EnrichmentModelProcessorBase]): The model processor class for enrichment.
            enrichment_transformer (Type[EnrichmentTransformerBase]): The transformer class for enrichment.
            inline_params (Optional[Dict[str, Any]]): Optional inline parameters for the service.
            one_lake_endpoint (str): The endpoint for OneLake. Defaults to GC.DEFAULT_ONE_LAKE_ENDPOINT.
            mssparkutils_client (Optional[MSSparkUtilsClientBase]): Optional MSSparkUtils client.
        """
        try:
            self.spark = spark
            self.workspace_name = workspace_name
            self.solution_name = solution_name
            self.mssparkutils_client = Utils.get_mssparkutils_client(mssparkutils_client)
            self.one_lake_endpoint = one_lake_endpoint
            self._logger = LoggingHelper.get_ai_enrichment_execution__logger(
                self.spark, self.__class__.__name__, GC.LOGGING_LEVEL
            )

            self.parameter_service = ParameterService(
                spark=spark,
                workspace_name=workspace_name,
                admin_lakehouse_name=admin_lakehouse_name,
                one_lake_endpoint=self.one_lake_endpoint,
                mssparkutils_client=self.mssparkutils_client,
                inline_params=inline_params,
            )
            
            self._logger.info(f"{LC.AI_ENRICHMENT_ENRICHMENT_METADATA_SERVICE_INIT_START}")
            
            # Metadata operations: create/retrieve enrichment views and handle enrichment definitions
            self.metadata = AIEnrichmentsMetaDataService(
                workspace_name=workspace_name,
                solution_name=solution_name,
                admin_lakehouse_name=admin_lakehouse_name,
                one_lake_endpoint=one_lake_endpoint,
                mssparkutils_client=mssparkutils_client,
                spark=spark,
                inline_params=inline_params
            )
            
            self._logger.info(f"{LC.AI_ENRICHMENT_ENRICHMENT_EXECUTION_SERVICE_INIT_START}")
             
            # Execution logic using the provided model processor and transformer
            self.execution = AIEnrichmentsExecutionService(
                spark=spark,
                workspace_name=workspace_name,
                solution_name=solution_name,
                admin_lakehouse_name=admin_lakehouse_name,
                one_lake_endpoint=one_lake_endpoint,
                partition_config=partition_config,
                inline_params=inline_params,
                mssparkutils_client=mssparkutils_client,
                enrichment_model_processor=enrichment_model_processor,
                aienrichment_metadata_service=self.metadata,
                enrichment_transformer=enrichment_transformer,
                output_format=output_format
            )
        except Exception as e:
            raise EnrichmentServiceError(f"{LC.AI_ENRICHMENT_ENRICHMENT_SERVICE_INIT_ERROR}: {e}") from e
