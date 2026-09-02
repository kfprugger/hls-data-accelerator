# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------

from functools import partial
import hashlib
import uuid
from pyspark.sql import SparkSession, DataFrame, types as T, functions as F
from pyspark.sql.types import StringType
from pyspark.sql.functions import (
    col,
    when,
    from_json,
    explode,
    lit,
    get_json_object,
    udf,
    expr
)
from microsoft.fabric.hls.hds.structured_stream.delta_table_stream_reader import (
    DeltaTableStreamReader,
)
from microsoft.fabric.hls.hds.structured_stream.stream_orchestrator import (
    StreamOrchestrator,
    StreamingQueryInfo,
)
from microsoft.fabric.hls.hds.global_constants.global_constants import (
    GlobalConstants as GC,
)

from microsoft.fabric.hls.hds.flatten.constants import FlattenConstants as FC
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_logging_constants import AIEnrichmentsLoggingConstants as LC

from microsoft.fabric.hls.hds.flatten.normalization.normalization_manager import (
    FlattenNormalization,
)

from microsoft.fabric.hls.hds.utils.utils import FolderPath
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import (
    MSSparkUtilsClientBase,
)

from microsoft.fabric.hls.hds.utils.dataframe_utils import (
    upsert_unique_to_delta_managed,
    validate_checkpoint,
)
from microsoft.fabric.hls.hds.ai_enrichments.core.services.ai_enrichments_metadata_service import (
    AIEnrichmentsMetaDataService
)
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_constants import (
    AIEnrichmentsConstants as EC
)

from microsoft.fabric.hls.hds.ai_enrichments.core.utils.ai_enrichments_ingestion_utils import AIEnrichmentIngestionUtils as IngestionUtils
from microsoft.fabric.hls.hds.ai_enrichments.core.utils.ai_enrichments_utils import AIEnrichmentsUtils as AIEnrichmentsUtils

from microsoft.fabric.hls.hds.services.base_runnable_service import BaseRunnableService
from microsoft.fabric.hls.hds.data_models.execution_metadata import ExecutionMetadata, ExecutionDataType

@staticmethod
def get_hash_id(data: str) -> str:
    """
    Generate a hash ID for the given data.

    Args:
        data (str): The data to hash.

    Returns:
        str: The hash ID or empty string if data is None.
    """
    if not data:
        return ""

    return hashlib.sha256(data.encode('utf-8')).hexdigest()[:64]

@staticmethod
def get_unique_id() -> str:
    """
    Generate a unique ID.

    Returns:
        str: The unique ID.
    """
    return str(uuid.uuid4())
class AIEnrichmentsSilverIngestionService (BaseRunnableService):
    """
    The AIEnrichmentSilverIngestionService is responsible for ingesting data from
    a partitioned single source table in bronze lakehouse
    and applying the transformation function for known resources based on enrichment type.
    """

    def __init__(
        self,
        spark: SparkSession,
        workspace_name: str,
        solution_name: str,
        admin_lakehouse_name: str,
        inline_params: dict = None,
        one_lake_endpoint: str = GC.DEFAULT_ONE_LAKE_ENDPOINT,
        mssparkutils_client: MSSparkUtilsClientBase | None = None,
    ) -> None:
        """
        Args:
            spark: spark session
            workspace_name: Name of the Fabric Workspace
            solution_name: Name of the HDS-Healthcare data solutions OneLake workload solution
            admin_lakehouse_name (str): The lakehouse name of where the administration configurations are located
            inline_params (dict): Inline parameters that will overwrite and take precedence over the parameters
                                in the administration lakehouse configuration
            one_lake_endpoint (str): The one lake endpoint. Default is `onelake.dfs.fabric.microsoft.com`
            mssparksutils_client (MSSparkUtilsClientBase): The mssparkutils client
        """
        super().__init__ (
                spark=spark,
                workspace_name= workspace_name,
                solution_name= solution_name,
                one_lake_endpoint= one_lake_endpoint,
                inline_params= inline_params,
                admin_lakehouse_name= admin_lakehouse_name,
                mssparkutils_client= mssparkutils_client
        )
        
    def _setup(self):
        try:
            
            self._register_udfs()
        
            self.enrichment_metadata_service = AIEnrichmentsMetaDataService(
                spark=self.spark,
                workspace_name=self.workspace_name,
                solution_name=self.solution_name,
                admin_lakehouse_name=self.admin_lakehouse_name,
                one_lake_endpoint=self.one_lake_endpoint,
                inline_params=self.inline_params,
                mssparkutils_client=self.mssparkutils_client
            )
            
            self._init_config()
            
        except Exception as ex:
            self._logger.error(message=str(ex))
            raise

    def _register_udfs(self) -> None:
        """
        Registers required UDFs 
        """
        if not IngestionUtils.is_udf_registered(self.spark, FC.NORM_UDF_NORM_DATE):
            self.spark.udf.register(
                    FC.NORM_UDF_NORM_DATE,
                    FlattenNormalization.normalize_date,
                    T.TimestampType(),
                )

    
        self.spark.udf.register("hash_udf", get_hash_id, StringType())
        self.spark.udf.register("uuid_udf", get_unique_id, StringType())
                
    def _init_config(self) -> None:

        
        self.source_lakehouse_name = self.parameter_service.get_foundation_config_value(
            GC.BRONZE_LAKEHOUSE_ID_KEY
        )
        self.target_lakehouse_name = self.parameter_service.get_foundation_config_value(
            GC.SILVER_LAKEHOUSE_ID_KEY
        )

        self.max_files_per_trigger = self.parameter_service.get_activity_config_value(
            GC.MAX_FILES_PER_TRIGGER_KEY,
            GC.DEFAULT_NUMBER_OF_FILES_PER_TRIGGER_BRONZE,  # 1000
            "int",
        )
        self.max_bytes_per_trigger = self.parameter_service.get_activity_config_value(
            GC.MAX_BYTES_PER_TRIGGER_KEY,
            GC.DEFAULT_NUMBER_OF_BYTES_PER_TRIGGER_BRONZE,
            "int",
        )

        self.source_table_name = self.parameter_service.get_activity_config_value(
            EC.ENRICHMENT_SOURCE_TABLE_NAME_KEY,
            EC.DEFAULT_ENRICHMENT_TARGET_BRONZE_TABLE_NAME,
        )

        self.config_files_root_path = FolderPath.get_fabric_workload_files_root_path(
            workspace_name=self.workspace_name,
            one_lake_endpoint=self.one_lake_endpoint,
            solution_name=self.solution_name,
        )

        self.ai_enrichment_resource_schema_path = self.parameter_service.get_activity_config_value(
            GC.AI_ENRICHMENT_RESOURCE_SCHEMA_PATH_KEY,
            FolderPath.get_fabric_workload_files_ai_enrichment_resource_types_folder_path(
                root_path=self.config_files_root_path
            ),
        )

        self.target_tables_path = self.parameter_service.get_activity_config_value(
            GC.TARGET_TABLES_PATH_KEY,
            FolderPath.get_fabric_tables_path(
                workspace_name=self.workspace_name,
                one_lake_endpoint=self.one_lake_endpoint,
                lakehouse_name=self.target_lakehouse_name,
            ),
        )

        self.source_tables_path = self.parameter_service.get_activity_config_value(
            GC.SOURCE_TABLES_PATH_KEY,
            FolderPath.get_fabric_tables_path(
                workspace_name=self.workspace_name,
                one_lake_endpoint=self.one_lake_endpoint,
                lakehouse_name=self.source_lakehouse_name,
            ),
        )
        self.source_table_full_path = f"{self.source_tables_path}/{self.source_table_name}"

        self.checkpoint_path = self.parameter_service.get_activity_config_value(
            GC.CHECKPOINT_PATH_KEY,
            FolderPath.get_fabric_workload_files_checkpoint_folder_path(
                root_path=self.config_files_root_path,
                checkpoint_folder_name=self.target_lakehouse_name,
            ),
        )

        self.max_structured_streaming_queries = self.parameter_service.get_activity_config_value(
            GC.MAX_STRUCTURED_STREAMING_QUERIES_KEY,
            GC.DEFAULT_NUMBER_OF_MAX_STREAMING_QUERIES_BRONZE,  # 1
            "int",
        )

    def _execute(self, **kwargs) -> None:
        """
        Executes the AI Enrichments silver ingestion service.       
        """
        self.__ingest()
        
    def __ingest(self) -> None:
        """
        Ingest data from a partitioned single source table and apply the AI enrichment transformation
        function for known AI enrichment resources. This method sets up a streaming query per resource type
        and awaits the completion of all streaming queries.
        """
        try:

            stream_orchestrator = StreamOrchestrator(
                spark=self.spark,
                max_structured_streaming_queries=self.max_structured_streaming_queries,
            )

            # Initialize streaming from source
            delta_table_stream_reader = self._initialize_delta_stream_reader()
            streaming_dataframe = delta_table_stream_reader.set_up_streaming(
                delta_table_path=self.source_table_full_path
            )
            # Read and gather distinct resource types
            resource_types_df = self.spark.read.format("delta").load(self.source_table_full_path)
            resource_types = (
                resource_types_df
                .select(EC.ENRICHMENT_BRONZE_ENRICHMENT_TYPE_COLUMN)
                .distinct()
                .rdd.flatMap(lambda x: x)
                .collect()
            )

            # Create a streaming query for each resource type
            for resource_type in resource_types:
                resource_streaming_df = streaming_dataframe.filter(
                    col(EC.ENRICHMENT_BRONZE_ENRICHMENT_TYPE_COLUMN) == resource_type
                )

                query_info = self._create_streaming_query_info_for_resource(
                    resource_type=resource_type,
                    target_table_path=f"{self.target_tables_path}/{AIEnrichmentsUtils.format_output_type_for_output_path(resource_type)}{EC.ENRICHMENT_SUFFIX}",
                    streaming_df=resource_streaming_df,
                )
                if query_info:
                    stream_orchestrator.enqueue_streaming_query(query_info)

            stream_orchestrator.await_all()
        except Exception as ex:
            message = LC.AI_ENRICHMENT_SILVER_INGESTION_EXECUTION_ERROR.format(error=ex)
            self._logger.error(message)
            raise ex
        
    def _create_streaming_query_info_for_resource(
        self,
        resource_type: str,
        target_table_path: str,
        streaming_df: DataFrame,
    ) -> StreamingQueryInfo | None:
        """
        Build the settings for a streaming query on a given resource type.
        Returns a StreamingQueryInfo object if the resource schema is found.
        """
        try:
            # Retrieve schema for resource
            resource_schema_path = f"{self.ai_enrichment_resource_schema_path}/{resource_type.lower()}.json"
            resource_schema = IngestionUtils.get_schema_from_json_file(self.spark, resource_schema_path)

            if resource_schema is None:
                raise Exception(
                    EC.ENRICHMENT_RESOURCE_SCHEMA_NOT_FOUND_ERROR_MSG.format(resource_type)
                )

            resource_checkpoint_path = (
                f"{self.checkpoint_path}/{EC.ENRICHMENT_SILVER_CHECKPOINT_FOLDER}/{resource_type}"
            )

            # Prepare partial for batch processing
            batch_fn = partial(
                self._batch_process_resource_data,
                resource_schema=resource_schema,
                target_table_path=target_table_path,
                enrichment_type=resource_type,
            )

            validate_checkpoint(
                spark=self.spark,
                logger=self._logger,
                target_table_path=target_table_path,
                checkpoint_path=resource_checkpoint_path,
                mssparkutils_client=self.mssparkutils_client,
                resource_name=resource_type,
            )

            return StreamingQueryInfo(
                query_name=f"{self.source_table_full_path}_{self.target_tables_path}_{resource_type}",
                checkpoint_path=resource_checkpoint_path,
                streaming_dataframe=streaming_df,
                batch_fn=batch_fn,
                data_format="delta",
            )
        except Exception as e:
            self._logger.error(
                LC.AI_ENRICHMENT_SILVER_FAILED_TO_STREAM_RESOURCE_ERROR_MSG.format(
                    resource_name=resource_type, exception_details=str(e)
                )
            )
            return None

    def _batch_process_resource_data(
        self,
        df: DataFrame,
        batchId: int,
        resource_schema: T.StructType,
        target_table_path: str,
        enrichment_type: str,
    ) -> None:
        """
        Batch function for processing resource data. Parses and transforms common fields,
        applies resource-specific schema, and upserts to Delta.
        """
        df_common = self._parse_and_transform_common_context_data(df)
        if df_common is None:
            return

        df_parsed = df_common.withColumn(
            EC.ENRICHMENT_SILVER_PARSED_COLUMN,
            from_json(col(EC.ENRICHMENT_SILVER_VALUE_COLUMN), resource_schema)
        )

        # Generate final DataFrame for upsert
        selected_fields = IngestionUtils.get_silver_enrichment_table_fields(enrichment_type)
        enrichment_df = df_parsed.select(*selected_fields)

        upsert_unique_to_delta_managed(
            spark_session=self.spark,
            data_manager_logger=self._logger,
            df_to_process=enrichment_df,
            delta_table_path=target_table_path,
            unique_columns=[EC.ENRICHMENT_SILVER_UNIQUE_ID_COLUMN],
            source_modified_on_column=GC.DEFAULT_SILVER_MODIFIED_DATE_COL,
        )

        self._persist_enrichment_context_in_metadata_store(df_common)
                
        self.spark.sparkContext.setJobGroup(
            groupId=f"{self.__class__.__module__}.{self.__class__.__qualname__}",
            description=(
                f"""[AIEnrichmentsSilverIngestion] Counting total target records after upsert\n
                for batchId: {batchId}, enrichmentType: {enrichment_type}"""
            )
        )
        total_target_records = enrichment_df.count()
        self.execution_metrics_collector.accumulate(
            accumulator_activity_id = self.get_execution_metrics_accumulator_activity_id(),
            metrics = {"numTargetRecords": total_target_records}
        )
        

    def _parse_and_transform_common_context_data(
        self, df: DataFrame
    ) -> DataFrame | None:
        """
        Parse and transform the DataFrame for common context fields.
        """
        common_context_schema_path = f"{self.ai_enrichment_resource_schema_path}/{EC.ENRICHMENT_COMMON_SCHEMA_NAME}.json"
        common_context_schema = IngestionUtils.get_schema_from_json_file(
            self.spark, common_context_schema_path
        )

        try:
            df = df.withColumn(
                EC.ENRICHMENT_SILVER_PARSED_COLUMN,
                from_json(col(EC.ENRICHMENT_SILVER_DATA_COLUMN), common_context_schema),
            )

            df = df.select(
                get_json_object(col(EC.ENRICHMENT_SILVER_DATA_COLUMN), EC.ENRICHMENT_JSON_PATH_CONTEXT)
                .cast("string")
                .alias(EC.ENRICHMENT_CONTEXT_COLUMN),
                when(
                        col(EC.ENRICHMENT_PARSED_CONTEXT_ID).isNotNull(),
                        col(EC.ENRICHMENT_PARSED_CONTEXT_ID)
                    ).otherwise(expr(f"hash_udf({EC.ENRICHMENT_CONTEXT_COLUMN})")).alias(EC.ENRICHMENT_CONTEXT_ID_COLUMN),                
                col(EC.ENRICHMENT_CONTEXT_MODEL_CONFIGURATION_NAME).alias(EC.ENRICHMENT_SILVER_MODEL_NAME_COLUMN),
                col(EC.ENRICHMENT_CONTEXT_MODEL_CONFIGURATION_VERSION).alias(EC.ENRICHMENT_SILVER_MODEL_VERSION_COLUMN),
                col(EC.ENRICHMENT_CONTEXT_ENRICHMENT_INPUT_PATIENT_ID).alias(EC.ENRICHMENT_SILVER_PATIENT_ID_COLUMN),
                col(EC.ENRICHMENT_CONTEXT_ENRICHMENT_INPUT_METADATA).alias(EC.ENRICHMENT_SILVER_METADATA_COLUMN),
                col(EC.ENRICHMENT_PARSED_GENERATION_ID).alias(EC.ENRICHMENT_GENERATION_ID_COLUMN),
                col(EC.ENRICHMENT_PARSED_DEFINITION_ID).alias(EC.ENRICHMENT_DEFINITION_ID_COLUMN),
                explode(col(EC.ENRICHMENT_PARSED_OUTPUTS)).alias(EC.ENRICHMENT_SILVER_OUTPUTS_COLUMN),
                col(EC.ENRICHMENT_OUTPUT_VALUE).alias(EC.ENRICHMENT_SILVER_VALUE_COLUMN),
                when(col(EC.ENRICHMENT_OUTPUT_CONFIDENCE_SCORE) == 0.0, lit(""))
                .otherwise(col(EC.ENRICHMENT_OUTPUT_CONFIDENCE_SCORE)).alias(EC.ENRICHMENT_SILVER_CONFIDENCE_SCORE_COLUMN),
                col(EC.ENRICHMENT_OUTPUT_DESCRIPTION).alias(EC.ENRICHMENT_SILVER_DESCRIPTION_COLUMN),
                col(EC.ENRICHMENT_BRONZE_FULL_FILE_PATH_COLUMN),
            ).withColumn(
                EC.ENRICHMENT_SILVER_UNIQUE_ID_COLUMN, F.expr("uuid()")
            )

            return df
        except Exception as e:
            self._logger.error(EC.ENRICHMENT_FAILED_TO_PARSE_COMMON_CONTEXT_ERROR_MSG.format(e))
            return None

    def _persist_enrichment_context_in_metadata_store(self, df: DataFrame) -> None:
        """
        Persists the enrichment context data by adding hash-based and UUID-based IDs,
        then saving the result with the metadata service.
        """

        df_to_save = df.withColumn(
                EC.ENRICHMENT_UNIQUE_ID_COLUMN, F.expr("uuid_udf()")  # Generate unique enrichment ID
            ).select(
                EC.ENRICHMENT_CONTEXT_ID_COLUMN,
                EC.ENRICHMENT_CONTEXT_COLUMN,
                EC.ENRICHMENT_GENERATION_ID_COLUMN,
                EC.ENRICHMENT_UNIQUE_ID_COLUMN,
            )

        try:
            self.enrichment_metadata_service.save_enrichment_contexts(df_to_save)
        except Exception as e:
            self._logger.error(EC.ENRICHMENT_CONTEXT_SAVE_ERROR_MSG.format(e))

    def _initialize_delta_stream_reader(self) -> DeltaTableStreamReader:
        """
        Create and configure a DeltaTableStreamReader with optional triggers.
        """
        stream_reader_kwargs = {}

        if self.max_bytes_per_trigger:
            stream_reader_kwargs["maxBytesPerTrigger"] = self.max_bytes_per_trigger

        if self.max_files_per_trigger:
            stream_reader_kwargs["maxFilesPerTrigger"] = self.max_files_per_trigger

        return DeltaTableStreamReader(self.spark, **stream_reader_kwargs)

    def _setup_execution_metadata(self):
        source_lakehouse_properties = self.mssparkutils_client.get_lakehouse(self.source_lakehouse_name)
        target_lakehouse_properties = self.mssparkutils_client.get_lakehouse(self.target_lakehouse_name)
        return ExecutionMetadata(
            sourceType=ExecutionDataType.deltaTable,
            sourcePath=self.source_tables_path,
            sourceLakehouseName=source_lakehouse_properties.get("displayName"),
            sourceLakehouseIdentifier=source_lakehouse_properties.get("id"),
            targetType=ExecutionDataType.deltaTable,
            targetPath=self.target_tables_path,
            targetLakehouseName=target_lakehouse_properties.get("displayName"),
            targetLakehouseIdentifier=target_lakehouse_properties.get("id")
        )
    
    def _get_internal_activity_name(self):
        return EC.ENRICHMENT_SILVER_INGESTION_ACTIVITY_NAME
    