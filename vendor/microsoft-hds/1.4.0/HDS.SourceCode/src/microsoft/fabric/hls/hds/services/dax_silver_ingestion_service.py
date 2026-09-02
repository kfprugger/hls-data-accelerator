# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
from functools import partial
import hashlib
import json
from typing import Callable, Tuple, Union
from datetime import datetime

from pyspark.sql import SparkSession, DataFrame, types as T, functions as F
from microsoft.fabric.hls.hds.flatten.normalization.identifier_normalization import IdentifierNormalization
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
from microsoft.fabric.hls.hds.global_constants.logging_constants import (
    LoggingConstants as LC,
)
from microsoft.fabric.hls.hds.flatten.normalization.normalization_manager import FlattenNormalization

from microsoft.fabric.hls.hds.utils.utils import FolderPath, Utils
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import (
    MSSparkUtilsClientBase,
)

from microsoft.fabric.hls.hds.utils.dataframe_utils import (
    upsert_unique_to_delta_managed,
    validate_checkpoint,
)
from microsoft.fabric.hls.hds.services.base_runnable_service import BaseRunnableService
from microsoft.fabric.hls.hds.data_models.execution_metadata import ExecutionMetadata, ExecutionDataType

class DaxSilverIngestionService (BaseRunnableService):
    """
    The DaxSilverIngestionService is responsible for ingesting data from 
    a partitioned single source table and applying the dax transformation function for known resources.
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
        - workspace_name: Name of the Fabric Workspace
        - solution_name: Name of the HDS-Healthcare data solutions OneLake workload solution
        - admin_lakehouse_name (str): The lakehouse name of where the administration configurations are located
        - inline_params (dict): Inline parameters that will overwrite and take precedence over the parameters in the administration lakehouse configuration
        - one_lake_endpoint (str): The one lake endpoint. Default is `onelake.dfs.fabric.microsoft.com`
        - mssparksutils_client (MSSparkUtilsClientBase): The mssparkutils client
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
        
        def __check_udf_registered(udf_name: str) -> bool:
            """
            Check if UDF is registered in spark session
            """
            # Use SQL to check if the UDF exists (works if it's globally registered)
            try:
                result = self.spark.sql(f"SHOW FUNCTIONS LIKE '{udf_name}'").collect()
                return len(result) > 0
            except Exception as e:
                print(f"Error checking UDF registration: {e}")
            return False
            
        self.source_lakehouse_name = self.parameter_service.get_foundation_config_value(GC.BRONZE_LAKEHOUSE_ID_KEY)
        self.target_lakehouse_name = self.parameter_service.get_foundation_config_value(GC.SILVER_LAKEHOUSE_ID_KEY)

        self.max_files_per_trigger = self.parameter_service.get_activity_config_value(
            GC.MAX_FILES_PER_TRIGGER_KEY, 
            GC.DEFAULT_NUMBER_OF_FILES_PER_TRIGGER_BRONZE, # 1000 
            "int"
        )

        self.max_bytes_per_trigger = self.parameter_service.get_activity_config_value(
            GC.MAX_BYTES_PER_TRIGGER_KEY, 
            GC.DEFAULT_NUMBER_OF_BYTES_PER_TRIGGER_BRONZE, 
            "int"
        )

        self.source_table_name = self.parameter_service.get_activity_config_value(
            GC.DAX_SOURCE_TABLE_NAME_KEY,
            GC.DEFAULT_DAX_TARGET_BRONZE_TABLE_NAME
        )
        
        try:
            self.target_tables_path = self.parameter_service.get_activity_config_value(
                GC.TARGET_TABLES_PATH_KEY,
                FolderPath.get_fabric_tables_path(
                    workspace_name=self.workspace_name,
                    one_lake_endpoint=self.one_lake_endpoint,
                    lakehouse_name=self.target_lakehouse_name,
                )
            )
            
            self.source_tables_path = self.parameter_service.get_activity_config_value(
                GC.SOURCE_TABLES_PATH_KEY,
                FolderPath.get_fabric_tables_path(
                    workspace_name=self.workspace_name,
                    one_lake_endpoint=self.one_lake_endpoint,
                    lakehouse_name=self.source_lakehouse_name,
                )
            )
            
            self.dax_resource_schema_path = self.parameter_service.get_activity_config_value(
                GC.DAX_RESOURCE_SCHEMA_PATH_KEY,
                FolderPath.get_fabric_workload_files_dax_resources_folder_path(root_path=self.config_files_root_path)
            )

            self.source_table_full_path = (
                f"{self.source_tables_path}/{self.source_table_name}"
            )

            self.checkpoint_path = self.parameter_service.get_activity_config_value(
                GC.CHECKPOINT_PATH_KEY,
                FolderPath.get_fabric_workload_files_checkpoint_folder_path(root_path=self.config_files_root_path,
                                                                            checkpoint_folder_name=self.target_lakehouse_name)
            )

            self.max_structured_streaming_queries = self.parameter_service.get_activity_config_value(
                GC.MAX_STRUCTURED_STREAMING_QUERIES_KEY, 
                GC.DEFAULT_NUMBER_OF_MAX_STREAMING_QUERIES_BRONZE, # 1
                "int"
            )

            if not __check_udf_registered(FC.NORM_UDF_NORM_DATE):
                self.spark.udf.register(
                    FC.NORM_UDF_NORM_DATE,
                    FlattenNormalization.normalize_date,
                    T.TimestampType(),
                )

        except Exception as ex:
            self._logger.error(message=str(ex))
            raise

    def _create_streaming_query_info(
        self,
        resource_type: str,
        resource_path: str,
        target_table_path: str,
        resource_fn: Callable,
        streaming_df: DataFrame,
    ) -> StreamingQueryInfo | None:
        """
        Stream a resource and apply the resource function to the stream

        Args:
        - resource_type: str - The type of the resource (Transcript, Note, etc.)
        - resource_path: str - The path to the resource
        - resource_fn: Callable - The function to apply to the resource
        - streaming_df: DataFrame - The streaming DataFrame
        Returns:
        - StreamingQueryInfo | None: The streaming query info
        """
        try:
            resource_schema = self._get_resource_schema(resource_type)
            if resource_schema is None:
                self._logger.warning(
                    LC.DAX_INGESTION_TRANSFORMATION_NO_SCHEMA.format(
                        resource_name=resource_type, source_table_path=resource_path
                    )
                )
                return None

            resource_checkpoint_path = (
                f"{self.checkpoint_path}/dax_silver/{resource_type}"
            )

            batch_fn = partial(
                resource_fn,
                resource=resource_type,
                resource_schema=resource_schema,
            )
            
            validate_checkpoint(spark=self.spark,
                logger=self._logger,
                target_table_path=target_table_path,
                checkpoint_path=resource_checkpoint_path,
                mssparkutils_client=self.mssparkutils_client,
                resource_name=resource_type)

            streaming_query_info = StreamingQueryInfo(
                query_name=f"{self.source_table_full_path}_{self.target_tables_path}_{resource_type}",
                checkpoint_path=resource_checkpoint_path,
                streaming_dataframe=streaming_df,
                batch_fn=batch_fn,
                data_format="delta",
            )
            return streaming_query_info
        except Exception as e:
            self._logger.error(
                LC.DAX_INGESTION_FAILED_TO_PROCESS_GENERIC_RESOURCE_ERROR_MSG.format(
                    resource_name=resource_type, exception_details=str(e)
                )
            )
            raise e

    def __ingest(self) -> None:
        """
        Ingest data from a partitioned single source table and apply the dax transformation function for known resources.

        This method sets up streaming on a single source table that is already partitioned by resource type,
        and applies the internal dax transformation function to each partition.

        """
        # Set up streaming on all source tables
        stream_orchestrator = StreamOrchestrator(
            spark=self.spark,
            max_structured_streaming_queries=self.max_structured_streaming_queries,
        )
        delta_table_stream_reader = self._get_delta_table_stream_reader()

        # Get all the resource types from the source table (identified by the parent folder column name)
        # Handle the column rename from 'parent_folder' to 'resource_type' and filter out NULLs
        # Try to get resource types, handling the case where parent_folder column might not exist
        try:
            # First try with both columns
            resource_types = (
                self.spark.sql(f"""
                    SELECT DISTINCT 
                        COALESCE(`{GC.DAX_BRONZE_FILE_TYPE_COLUMN}`, `{GC.DAX_BRONZE_PARENT_FOLDER_COLUMN}`) as resource_type
                    FROM delta.`{self.source_table_full_path}`
                    WHERE COALESCE(`{GC.DAX_BRONZE_FILE_TYPE_COLUMN}`, `{GC.DAX_BRONZE_PARENT_FOLDER_COLUMN}`) IS NOT NULL
                """)
                .rdd.flatMap(lambda x: x)
                .collect()
            )
        except Exception:
            # If that fails, try with just the file_type column
            try:
                resource_types = (
                    self.spark.sql(f"""
                        SELECT DISTINCT 
                            `{GC.DAX_BRONZE_FILE_TYPE_COLUMN}` as resource_type
                        FROM delta.`{self.source_table_full_path}`
                        WHERE `{GC.DAX_BRONZE_FILE_TYPE_COLUMN}` IS NOT NULL
                    """)
                    .rdd.flatMap(lambda x: x)
                    .collect()
                )
            except Exception:
                raise ValueError(f"Query failed for resource types: {self.source_table_full_path}")

            streaming_dataframe = delta_table_stream_reader.set_up_streaming(
                delta_table_path=self.source_table_full_path
            )

        for resource_type in resource_types:
            resource_type_streaming_df = streaming_dataframe.filter(
                streaming_dataframe[GC.DAX_BRONZE_FILE_TYPE_COLUMN] == resource_type
            )
            
            target_table_path = f"{self.target_tables_path}/{GC.DEFAULT_DAX_SILVER_PREFIX}{resource_type}"

            resource_streaming_query_info = self._create_streaming_query_info(
                resource_type=resource_type,
                resource_path=self.source_table_full_path,
                target_table_path=target_table_path,
                resource_fn=self._process_generic_dax_resource,
                streaming_df=resource_type_streaming_df,
            )
            if resource_streaming_query_info:
                stream_orchestrator.enqueue_streaming_query(resource_streaming_query_info)

        stream_orchestrator.await_all()

    def _get_delta_table_stream_reader(self) -> DeltaTableStreamReader:

        stream_reader_kwargs = {}

        self._logger.info(
            f"The maxBytesPerTrigger is set to {self.max_bytes_per_trigger}.The maxFilesPerTrigger is set to {self.max_files_per_trigger}."
        )
        if self.max_bytes_per_trigger:
            stream_reader_kwargs["maxBytesPerTrigger"] = self.max_bytes_per_trigger

        if self.max_files_per_trigger:
            stream_reader_kwargs["maxFilesPerTrigger"] = self.max_files_per_trigger

        return DeltaTableStreamReader(self.spark, **stream_reader_kwargs)

    def _get_resource_schema(self, resource: str) -> Union[T.StructType, None]:
        resource_path = (
            f"{self.dax_resource_schema_path}/{resource.lower()}.json"
        )

        if not Utils.file_exists(resource_path, self.mssparkutils_client):
            return None

        schema_str = Utils.load_config_file(self.spark, resource_path)
        schema_json = json.loads(schema_str)
        return T.StructType.fromJson(schema_json)


    def _process_dax_transcript_resource(
        self, df: DataFrame
    ) -> DataFrame:
        """
        Process the DAX transcript resource
        """

        def generate_transcript_id(source_system: str, transcript_id: str) -> str:
            """
            Generate a harmonized transcript id by hashing the concatenated string.
            
            Args:
                source_system (str): The source system identifier
                transcript_id (str): The transcript identifier

            Returns:
                str: SHA256 hash of the concatenated string
            """
            import hashlib
            if source_system is None or transcript_id is None:
                return None
                
            # Create the concatenated string following the pattern: <source_system>/DaxTranscript/<transcript_id>
            transcript_resource_url = f"{source_system}/DaxTranscript/{transcript_id}"

            link_encoded = transcript_resource_url.encode()
            hash_object = hashlib.sha256(link_encoded)
            return hash_object.hexdigest()

        def process_transcript(transcript): # pragma: no cover - not showing up in coverage report since it is called from UDF
            """
            Process the transcript data
            Args:
                transcript: The transcript data

            Returns:
                Tuple[str, str, float]: The conversation, webVTT, and total transcription time
            """
            conversation = ""
            webVTT = None
            total_transcription_time = 0.0

            if transcript is not None:
                # Process conversation
                conversation = "\n".join(
                    f"{turn['speaker']}: {turn['text']}" for turn in transcript["turns"]
                )
                webVTT = transcript["webVTT"]

                # Calculate transcription time
                try:
                    start_time = transcript["turns"][0]["start_time"]
                    end_time = transcript["turns"][-1]["end_time"]
                    time_difference = end_time - start_time
                    total_transcription_time = time_difference.total_seconds() / 60
                except Exception:
                    total_transcription_time = 0.0

            return conversation, webVTT, total_transcription_time

        # Define the UDF
        process_transcript_udf = F.udf(
            process_transcript,
            T.StructType(
                [
                    T.StructField("content", T.StringType(), True),
                    T.StructField("timeTranscript", T.StringType(), True),
                    T.StructField("totalTranscriptionTime",
                                  T.DoubleType(), True),
                ]
            ),
        )

        # Apply the UDF to the 'transcript' column to get the new columns
        dax_data_df = df.withColumn(
            "transcript_data", process_transcript_udf(F.col("transcript"))
        )

        # Now extract each field from the struct returned by the UDF
        dax_data_df = (
            dax_data_df.withColumn("content", F.col("transcript_data.content"))
            .withColumn("timeTranscript", F.col("transcript_data.timetranscript"))
            .withColumn(
                "totalTranscriptionTime",
                F.col("transcript_data.totalTranscriptionTime"),
            )
            .withColumn("encounterId", F.col("encounter.external_encounter_id"))
            .withColumn("patientId", F.col("encounter.patient.external_patient_id"))
            .withColumn("practitionerName", F.col("encounter.practitioner.full_name"))
        )
        dax_data_df = dax_data_df.drop("transcript_data")

        generate_transcript_udf = F.udf(generate_transcript_id, T.StringType())
        
        dax_df_with_id = dax_data_df.withColumn(
            "id", 
            generate_transcript_udf(
                F.col(GC.DEFAULT_SILVER_FHIR_TABLE_MSFT_SOURCE_SYSTEM_COL), 
                F.col("transcriptId")
            )
        )

        return dax_df_with_id

    def _process_generic_dax_resource(
        self,
        df: DataFrame,
        batchId: int,
        resource: str,
        resource_schema: T.StructType,
    ) -> None:
        """
        Process the generic DAX resource

        Args:
        - df: DataFrame - The DataFrame to process
        - batchid: int - The batch id
        - resource: str - The resource name
        - resource_schema: T.StructType - The resource schema
        """
        parsed_df = df.withColumn(
            "parsed_data",
            F.from_json(F.col(GC.DAX_BRONZE_FILE_CONTENT_COLUMN), resource_schema),
        )
        
        preprocess_df =parsed_df.select(
            *[
                F.col(f"parsed_data.{col_name}").alias(col_name)
                for col_name in resource_schema.fieldNames()
            ],  # Extract all columns from parsed_data
            F.regexp_extract(
                F.regexp_extract(GC.DAX_BRONZE_FULL_FILE_PATH_COLUMN, GC.DAX_BRONZE_FILENAME_REGEX, 1),
                GC.DAX_BRONZE_FILENAME_NO_EXTENSION_REGEX, 1
            ).alias(GC.DAX_SILVER_TRANSCRIPT_ID_COLUMN),
            F.col("createdDatetime").alias(GC.DEFAULT_SILVER_FHIR_TABLE_MSFT_CREATED_DATE_COL),  # Keep the original 'createdDatetime' column
            F.col(GC.DEFAULT_BRONZE_FHIR_TABLE_SOURCE_SYSTEM_COL)
                .alias(GC.DEFAULT_SILVER_FHIR_TABLE_MSFT_SOURCE_SYSTEM_COL),
            F.col(GC.DEFAULT_BRONZE_FHIR_TABLE_FILE_PATH_COL)
                .alias(GC.DEFAULT_SILVER_FHIR_TABLE_MSFT_FILE_PATH_COL)
        )

        unique_columns = [GC.DAX_SILVER_TRANSCRIPT_ID_COLUMN]
        source_modified_on_column = GC.DEFAULT_SILVER_FHIR_TABLE_MSFT_CREATED_DATE_COL

        # special processing for transcript resource
        if resource.casefold() == GC.DAX_TRANSCRIPT_RESOURCE_TYPE.casefold(): 
            # Process the transcript resource
            df = (self._process_dax_transcript_resource(preprocess_df))

        # Append the data to the target table
        upsert_unique_to_delta_managed(
            spark_session=self.spark,
            data_manager_logger=self._logger,
            df_to_process=df,
            delta_table_path=f"{self.target_tables_path}/{GC.DEFAULT_DAX_SILVER_PREFIX}{resource}",
            unique_columns=unique_columns,
            source_modified_on_column= source_modified_on_column,
        )
        
        total_target_records = df.count()
        self.execution_metrics_collector.accumulate(
            accumulator_activity_id = self.get_execution_metrics_accumulator_activity_id(),
            metrics = {"numTargetRecords": total_target_records}
        )

        
    def _get_internal_activity_name(self):
        return GC.DAX_SILVER_INGESTION_ACTIVITY_NAME
    
    def _execute(self, **kwargs):
        return self.__ingest()
    
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