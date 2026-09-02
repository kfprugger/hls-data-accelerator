import os
from functools import partial
from typing import List, Dict, Any
from delta import DeltaTable
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    col,
    input_file_name,
    from_json,
    explode,
    lit,
    get_json_object
)
from microsoft.fabric.hls.hds.utils.data_manager_logger import DataManagerLogger
from microsoft.fabric.hls.hds.global_constants.global_constants import (
    GlobalConstants as GC,
)
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_constants import (
    AIEnrichmentsConstants as EC,
)
from microsoft.fabric.hls.hds.structured_stream.stream_orchestrator import (
    StreamOrchestrator,
    StreamingQueryInfo,
)
from microsoft.fabric.hls.hds.structured_stream.file_stream_reader import (
    FileStreamReader,
)
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import (
    MSSparkUtilsClientBase,
)

class FHIRResourceExtractor:

    def __init__(
            self, 
            spark: SparkSession, 
            mssparkutils_client: MSSparkUtilsClientBase, 
            logger: DataManagerLogger,
            target_lakehouse_name: str,
            target_tables_path: str,
            checkpoint_path: str,
            max_structured_streaming_queries = GC.DEFAULT_NUMBER_OF_MAX_STREAMING_QUERIES_BRONZE,
            max_files_per_trigger = GC.DEFAULT_NUMBER_OF_FILES_PER_TRIGGER_BRONZE):
        
        self.spark = spark
        self.mssparkutils_client = mssparkutils_client
        self._logger = logger
        self.target_lakehouse_name = target_lakehouse_name
        self.target_tables_path = target_tables_path
        self.checkpoint_path = checkpoint_path
        self.max_structured_streaming_queries = max_structured_streaming_queries
        self.max_files_per_trigger = max_files_per_trigger
    
    def extract_fhir_resources(self, run_id):
        """
            Creates clinical files from the AI Enrichment objects.
        """
        self.run_id = run_id
        ai_enrichments_object_relative_path = f"/Files/Process/AIEnrichments/Object"
        ai_enrichments_fabric_path = f"{ai_enrichments_object_relative_path}/Fabric-HDS"
        ai_enrichments_object_output_path = f"{ai_enrichments_object_relative_path}/Output"
        clinical_ingestion_relative_path = f"/Files/Ingest/Clinical/FHIR-NDJSON/FHIR-HDS"

        intermediate_table_path = f"{self.target_tables_path}/{EC.AI_ENRICHMENT_FLAT_FHIR_OBJECT_TABLE_NAME}"

        root_lakehouse_dir = os.path.dirname(self.target_tables_path)
        source_folder_path = f"{root_lakehouse_dir}/{ai_enrichments_fabric_path}"

        if self.mssparkutils_client.fs_exists(source_folder_path):

            self.__flatten_enrichment_objects(source_folder_path, intermediate_table_path)

            # # Generate ndjson files
            formatted_file_directory = f"{root_lakehouse_dir}{ai_enrichments_object_output_path}"
            clinical_ingestion_directory = f"{root_lakehouse_dir}{clinical_ingestion_relative_path}"
            
            self.__generate_clinical_files(intermediate_table_path, formatted_file_directory)

            # # Move files to clinical ingestion folder, clean up temp resources
            self.__move_generated_files(formatted_file_directory, clinical_ingestion_directory)


    def __move_generated_files(self, source_folder_path: str, destination_folder_path: str) -> None:
        """
            Moves/rename the generated files from the source folder to the destination folder.
        """
        folder_paths = [file.path for file in  self.mssparkutils_client.fs_ls(source_folder_path)]

        for folder_path in folder_paths:
            
            file_paths = [file.path for file in  self.mssparkutils_client.fs_ls(folder_path)]
            for file_path in file_paths:

                if str(file_path).endswith("txt"):
                    resource_identifier = str(os.path.dirname(file_path)).split("/")[-1]
                    self._logger.info(f"moving resource: {resource_identifier} to path: {destination_folder_path}/{resource_identifier}_{self.run_id}.ndjson\n")
                    self.mssparkutils_client.fs_mv(file_path, f"{destination_folder_path}/{resource_identifier}_{self.run_id}.ndjson", create_path=True)
        
        self.mssparkutils_client.fs_rm(source_folder_path, recursive=True)

    def __expand_and_save_enrichments_objects(self, dataframe: DataFrame, batch_id: int, run_id: str, destination_folder_path: str) -> DataFrame:
        """
        Expands the enrichment objects to flat FHIR objects.
        """

        parsed_json_df = dataframe.select("source_file", from_json(col("value"), EC.AI_ENRICHMENT_OBJECT_TYPE_SCHEMA).alias("data"))

        resource_df = parsed_json_df \
            .withColumn("run_id", lit(run_id)) \
            .withColumn("output", explode(col("data.outputs"))) \
            .filter(col("output.value.type") == "FHIR") \
            .withColumn("resource_raw", explode(col("output.value.value"))) \
            .withColumn("resource_type", get_json_object(col("resource_raw"), "$.resourceType")) \
            .select(
                col("run_id"),
                col("data.context.enrichment_context_id").alias("enrichment_definition_id"), 
                col("resource_type"),
                col("source_file"),
                col("resource_raw").alias("resource")
            )
            
        resource_df.write.format("delta").mode("append").save(destination_folder_path)

    def __write_to_ndjson(self, batch_df: DataFrame, batch_id: int, resource_type: str, target_path: str) -> None:

        dir_name = f"{resource_type}_{batch_id}"
        dir_path = f"{target_path}/{dir_name}"

        # Pyspark json writer does not support writing to a single file, it will write to a folder
        # The generated file can be reconciled later
        batch_df.select(col("resource")).coalesce(1).write.option("header", "false").mode('overwrite').text(dir_path, lineSep="\n")

    def __flatten_enrichment_objects(self, source_folder_path: str, destination_table_path: str) -> DataFrame:
        """
        Flatten the enrichment objects to a flat FHIR resources and write to a delta table.
        """
        stream_orchestrator = StreamOrchestrator(self.spark, self.max_structured_streaming_queries)

        if DeltaTable.isDeltaTable(self.spark, destination_table_path) == False:

            df = self.spark.createDataFrame(data=[], schema=EC.AI_ENRICHMENT_FLAT_FHIR_OBJECT_SCEHMA)  
            df.write.format("delta").mode("overwrite").save(destination_table_path)

        checkpoint_path = f"{self.checkpoint_path}/{EC.ENRICHMENT_BRONZE_CHECKPOINT_FOLDER}/{EC.AI_ENRICHMENT_FLAT_FHIR_OBJECT_TABLE_NAME}/{self.run_id}"

        file_stream_reader = FileStreamReader(
            self.spark,
            maxFilesPerTrigger=self.max_files_per_trigger,
            recursiveFileLookup="true",
            pathGlobFilter="*.ndjson",
            multiline="true"
        )

        resource_streaming_df = (
            file_stream_reader.set_up_streaming_ndjson_string(
                streaming_path=source_folder_path,
            )
            .filter(input_file_name().endswith(".ndjson"))
        ).withColumn("source_file", input_file_name())

        batch_fn = partial(
            self.__expand_and_save_enrichments_objects,
            run_id=self.run_id if self.run_id else "placeholder_run_id",
            destination_folder_path=destination_table_path
        )

        streaming_query_info = StreamingQueryInfo(
            query_name=(
                f"ai_enrichment_processing.{EC.AI_ENRICHMENT_FLAT_FHIR_OBJECT_TABLE_NAME}"
            ),
            checkpoint_path=checkpoint_path,
            streaming_dataframe=resource_streaming_df,
            batch_fn=batch_fn,
            data_format="delta",
        )

        # Wait for flattening streaming query to complete
        stream_orchestrator.enqueue_streaming_query(streaming_query_info)
        stream_orchestrator.await_all()

        if stream_orchestrator.check_stream_success(streaming_query_info.query_name):
            self._logger.info(f"Successfully flattened enrichment objects to delta table.")
        else:
            self._logger.error(f"Failed to flatten enrichment objects to delta table.")
        
    def __generate_clinical_files(self, source_table_path: str, destination_directory: str) -> None:
        """
            Read from the intermediate flatten fhir resources table and generate ndjson files.
        """
        # Create a new streaming orchestrator to writing ndjson files
        stream_orchestrator = StreamOrchestrator(self.spark, self.max_structured_streaming_queries)

        resource_types = [
            row["resource_type"] for row in 
            self.spark.sql(f"SELECT Distinct(resource_type) FROM `{self.target_lakehouse_name}`.{EC.AI_ENRICHMENT_FLAT_FHIR_OBJECT_TABLE_NAME}").collect()
        ]

        for resource_type in resource_types:

            resource_checkpoint_path = f"{self.checkpoint_path}/{EC.ENRICHMENT_BRONZE_CHECKPOINT_FOLDER}/{EC.AI_ENRICHMENT_FLAT_FHIR_OBJECT_TABLE_NAME}/{self.run_id}/{resource_type}"                        
            resource_streaming_df = self.spark.readStream \
                .format("delta") \
                .option("maxFilesPerTrigger", self.max_files_per_trigger) \
                .load(source_table_path) \
                .filter((col("run_id") == self.run_id) & (col("resource_type") == resource_type))
            
            self.mssparkutils_client.fs_mkdirs(destination_directory)

            batch_fn = partial(
                self.__write_to_ndjson,
                resource_type=resource_type,
                target_path=destination_directory)

            streaming_query_info = StreamingQueryInfo(
                query_name=(
                    f"ai_enrichment_processing.{EC.AI_ENRICHMENT_FLAT_FHIR_OBJECT_TABLE_NAME}-{resource_type}"
                ),
                checkpoint_path=resource_checkpoint_path,
                streaming_dataframe=resource_streaming_df,
                batch_fn=batch_fn
            )
            
            stream_orchestrator.enqueue_streaming_query(streaming_query_info)

        stream_orchestrator.await_all()