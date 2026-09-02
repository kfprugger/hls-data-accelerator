# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import gzip
import io
import json
import logging
import os
from typing import Any, Dict, Iterable, List, Literal, Type, Optional, Tuple, Union
import uuid
import zipfile
import pandas as pd
import pyspark
from pyspark import TaskContext
from microsoft.fabric.hls.hds.ai_enrichments.core.errors.execution_service_error import ExecutionServiceError
from microsoft.fabric.hls.hds.ai_enrichments.core.errors.model_configuration_error import ModelConfigurationError
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.metadata.enrichment_input_mapping import EnrichmentInputMapping
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_context import EnrichmentContext
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_result import EnrichmentResult
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from pyspark.sql import SparkSession
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.metadata.enrichment_view import EnrichmentView
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.metadata.generated_enrichment import GeneratedEnrichment
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_input import EnrichmentInput
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.enrichment_result import EnrichmentResult
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.output.resource_reference import ResourceReference
from microsoft.fabric.hls.hds.ai_enrichments.core.base_classes.enrichment_model_processor_base import EnrichmentModelProcessorBase
from microsoft.fabric.hls.hds.ai_enrichments.core.base_classes.enrichment_transformer_base import EnrichmentTransformerBase
from microsoft.fabric.hls.hds.ai_enrichments.core.utils.ai_enrichments_utils import AIEnrichmentsUtils
from microsoft.fabric.hls.hds.ai_enrichments.core.services.ai_enrichments_metadata_service import AIEnrichmentsMetaDataService
from microsoft.fabric.hls.hds.utils.logging_helper import LoggingHelper
from microsoft.fabric.hls.hds.utils.parameter_service import ParameterService
from microsoft.fabric.hls.hds.utils.utils import FolderPath, Utils
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_logging_constants import AIEnrichmentsLoggingConstants as ELC
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_constants import AIEnrichmentsConstants as EC     
from pyspark.sql import Row

from microsoft.fabric.hls.hds.utils.worker_execution_logger import WorkerExecutionLogger


class AIEnrichmentsExecutionService:
    """
    AIEnrichmentsExecutionService is responsible for managing the enrichment process within the healthcare data platform.
    """

    def __init__(
        self,
        spark: SparkSession,
        workspace_name: str,
        solution_name: str,
        admin_lakehouse_name: str,
        enrichment_model_processor: Type[EnrichmentModelProcessorBase],
        enrichment_transformer: Type[EnrichmentTransformerBase],
        aienrichment_metadata_service: AIEnrichmentsMetaDataService,
        partition_config: dict =EC.ENRICHMENT_PARTITION_CONFIG_DEFAULT,
        inline_params: Optional[Dict[str, Any]] = None,
        one_lake_endpoint: str = GC.DEFAULT_ONE_LAKE_ENDPOINT,
        output_format:Literal["json","ndjson"] = "ndjson",
        mssparkutils_client: Optional[MSSparkUtilsClientBase] = None
    ) -> None:
        """
        Initializes the AIEnrichmentsExecutionService with the provided parameters.

        Args:
            spark (SparkSession): The Spark session to use for data processing.
            workspace_name (str): The name of the workspace.
            solution_name (str): The name of the solution.
            admin_lakehouse_name (str): The name of the admin lakehouse.
            enrichment_model_processor (Type[EnrichmentModelProcessorBase]): The processor for enrichment models.
            enrichment_transformer (Type[EnrichmentTransformerBase]): The transformer for enrichment data.
            aienrichment_metadata_service (AIEnrichmentsMetaDataService): The service for enrichment metadata operations.
            inline_params (Optional[Dict[str, Any]], optional): Custom inline parameters for activity configuration.
            one_lake_endpoint (str, optional): The endpoint for OneLake. Defaults to GC.DEFAULT_ONE_LAKE_ENDPOINT.
            output_format (Literal["json","ndjson"], optional): The output format. Defaults to "ndjson".
            mssparkutils_client (Optional[MSSparkUtilsClientBase], optional): The MSSparkUtils client. Defaults to None.
            new_param (Optional[Any], optional): New optional parameter to demonstrate docstring update.

        Raises:
            Exception: If an error occurs during initialization.
        """
        try:
            self.spark = spark
            self.workspace_name = workspace_name
            self.solution_name = solution_name
            self.mssparkutils_client = Utils.get_mssparkutils_client(mssparkutils_client)
            self.one_lake_endpoint = one_lake_endpoint
            self.parameter_service = ParameterService(
                spark=spark,
                workspace_name=workspace_name,
                admin_lakehouse_name=admin_lakehouse_name,
                one_lake_endpoint=self.one_lake_endpoint,
                mssparkutils_client=self.mssparkutils_client,
                inline_params=inline_params,
            )
            self.target_lakehouse_name = self.parameter_service.get_foundation_config_value(GC.BRONZE_LAKEHOUSE_ID_KEY)
            self.silver_lakehouse_id = self.parameter_service.get_foundation_config_value(
                GC.SILVER_LAKEHOUSE_ID_KEY
            )
            self.enrichment_records_limit = int(self.parameter_service.get_activity_config_value(
                EC.ENRICHMENT_RECORDS_LIMIT_KEY, EC.ENRICHMENT_RECORDS_LIMIT_DEFAULT_VALUE
            ))
            
            self.enrichment_output_records_limit_per_file = int(self.parameter_service.get_activity_config_value(
                EC.ENRICHMENT_RECORDS_OUTPUT_LIMIT_KEY, EC.ENRICHMENT_RECORDS_OUTPUT_LIMIT_DEFAULT_VALUE
            ))

            self.enrichment_collect_batch_size = int(self.parameter_service.get_activity_config_value(
                EC.ENRICHMENT_EXECUTION_COLLECT_BATCH_SIZE_KEY, EC.ENRICHMENT_EXECUTION_COLLECT_BATCH_SIZE_DEFAULT_VALUE
            ))
        
            self.should_save_model_raw_response = bool(self.parameter_service.get_activity_config_value(
                EC.ENRICHMENT_RECORDS_SAVE_RAW_RESPONSE_KEY, False
            ))
            
            self.enrichment_model_defintion_excluded_keys = str(self.parameter_service.get_activity_config_value(
                EC.ENRICHMENT_MODEL_CONFIG_EXCLUDE_KEYS, EC.ENRICHMENT_MODEL_CONFIG_EXCLUDE_VALUES
            ))
          
            if enrichment_model_processor is None or enrichment_transformer is None:
                raise ExecutionServiceError(ELC.AI_ENRICHMENT_ENRICHMENT_SERVICE_INIT_ERROR)
            self.enrichment_metadata_service = aienrichment_metadata_service
            self.enrichment_transformer = enrichment_transformer
            self.enrichment_model_processor = enrichment_model_processor
         
            self.landing_zone_lakehouse_id = self.parameter_service.get_activity_config_value(
                EC.ENRICHMENT_LANDING_ZONE_LAKEHOUSE_ID_KEY, self.target_lakehouse_name
            )
            self.execution_threads = self.parameter_service.get_activity_config_value(
                    EC.DEFAULT_AI_ENRICHMENT_EXECUTION_THREADS_LIMIT_KEY,
                    EC.DEFAULT_AI_ENRICHMENT_EXECUTION_THREADS,
                    "int"
            )
            
            self.metadata_lakehouse_id = (self.parameter_service.get_foundation_config_value(EC.ENRICHMENT_METADATA_LAKEHOUSE_ID_KEY))
         
            self._logger = LoggingHelper.get_ai_enrichment_execution__logger(
                self.spark, self.__class__.__name__, GC.LOGGING_LEVEL
            )
            self.output_format=output_format
            
             # Retrieve the Key Vault name from the foundation configuration
            self.kv_name = self.parameter_service.get_foundation_config_value(GC.KEYVAULT_NAME_KEY)
            self._initialize_paths()
            n_part_exec = partition_config.get(EC.ENRICHMENT_EXECUTION_PARTITION, EC.ENRICHMENT_EXECUTION_PARTITION_VALUE)
            if not isinstance(n_part_exec, int) or n_part_exec < 1:
                raise ValueError(ELC.AI_ENRICHMENT_INVALID_ENRICHMENT_EXECUTION_PARTITION)
            n_part_save = partition_config.get(EC.ENRICHMENT_SAVE_PARTITION, EC.ENRICHMENT_SAVE_PARTITION_VALUE)
            if not isinstance(n_part_save, int) or n_part_save < 1:
                raise ValueError(ELC.AI_ENRICHMENT_INVALID_ENRICHMENT_SAVE_PARTITION)
            execution_mode = partition_config.get(EC.ENRICHMENT_EXECUTION_MODE, EC.ENRICHMENT_EXECUTION_MODE_VALUES[0]).lower()
            if execution_mode != "driver":
                execution_mode = "distributed"
            partition_config = {
                EC.ENRICHMENT_EXECUTION_PARTITION: n_part_exec,
                EC.ENRICHMENT_SAVE_PARTITION: n_part_save,
                EC.ENRICHMENT_EXECUTION_MODE: execution_mode
            }
            self.partition_config = partition_config

        except Exception as e:
            self._logger.error(f"{ELC.AI_ENRICHMENT_ENRICHMENT_SERVICE_INIT_ERROR}: {e}")
            raise

    def execute(self, enrichment_id: str) -> None:
        """
        Executes the enrichment process for a given enrichment ID.

        Args:
            enrichment_id (str): The ID of the enrichment process to execute.

        Raises:
            Exception: If any error occurs during the enrichment process, it is logged and re-raised.
        """
        try:
            self._logger.info(f"{ELC.AI_ENRICHMENT_ENRICHMENT_SERVICE_START}: {enrichment_id}")

            # prepare for execution: init, validate, and set miscellaneous fields
            self._setup_enrichment_metadata(enrichment_id)

            # prepare the input data frame. Note the repartitioning, if needed.
            input_df = self._run_enrichment_definition()
            n_rows_to_process = input_df.count()
            if n_rows_to_process == 0:
                self._logger.warning(EC.ENRICHMENT_VIEW_QUERY_RESULT_EMPTY.format(enrichment_view_info_id=self.enrichment_definition.view_id))
                return
            
            # execute: driver or distribution mode.
            if self.partition_config[EC.ENRICHMENT_EXECUTION_MODE] == "driver":
                n_active_contexts = self._run_driver_mode(input_df)
            else:
                n_active_contexts = self._run_distributed_mode(input_df)

            if n_active_contexts == 0:
                self._logger.warning(ELC.AI_ENRICHMENT_NO_ACTIVE_ENRICHMENT_CONTEXTS.format(generation_id=self.enrichment_generation_id))
                return
            

            generated_enrichment_info = GeneratedEnrichment(
                id= self.enrichment_generation_id,
                materialize_view_id=self.materialized_id,
                input_name=self.input_table_name,
                name=f"Generated enrichment for {enrichment_id}"
            )

            self.enrichment_metadata_service.create_generated_enrichment(generated_enrichment_info)
                
            self._logger.info(f"{ELC.AI_ENRICHMENT_ENRICHMENT_SERVICE_SUCCESS}: {enrichment_id}")
            
        except Exception as e:
            raise ExecutionServiceError(f"{ELC.AI_ENRICHMENT_ENRICHMENT_EXECUTION_ERROR}: {e}") from e
    

    def _run_driver_mode(self, input_df: pyspark.sql.DataFrame) -> int:
        """
        Driver mode processing of the enrichment input and returns the transformed enriched response.

        Args:
            input_df (pyspark.sql.DataFrame): The input dataframe for the enrichment process.

        Returns:
            int: The number of active enrichment contexts processed.
        """
        try:
            input_records_to_process = [row.asDict() for row in input_df.collect()]
            enrichment_input_contexts_list = self._construct_active_enrichment_contexts(input_records_to_process)
            if self.enrichment_records_limit > 0:
                enrichment_input_contexts_list = enrichment_input_contexts_list[:self.enrichment_records_limit]

            n_active_contexts = len(enrichment_input_contexts_list)
            self._logger.info(ELC.AI_ENRICHMENT_EXECUTE_STARTED_INFO.format(inputs_count=n_active_contexts, generation_id= self.enrichment_generation_id))
            if n_active_contexts > 0:
                self._logger.info(f"{ELC.AI_ENRICHMENT_MODEL_PROCESS_EXECUTION_INFO.format(records_count=n_active_contexts)}")

                raw_responses = self.enrichment_model_processor.process(
                    self.enrichment_generation_id,
                    self.model_config,
                    enrichment_input_contexts_list,
                )

                if len(raw_responses) == 0:
                    raise ExecutionServiceError(ELC.AI_ENRICHMENT_MODEL_PROCESS_EMPTY_RESPONSE_ERROR)

                # Transform the raw responses to enriched responses
                self._logger.info(f"{ELC.AI_ENRICHMENT_TRANSFORMER_PROCESS_STARTED_INFO}")
                transformed_responses: List[EnrichmentResult] = self.enrichment_transformer.transform(
                    self.enrichment_generation_id,
                    enrichment_input_contexts_list,
                    raw_responses,
                )

                # loop through the transformed responses and update enrichment definition id
                for response in transformed_responses:
                    response.enrichment_definition_id= self.enrichment_definition_id
                    if response.context.enrichment_input.image_file_references and len(response.context.enrichment_input.image_file_references) > 0:
                            response.context.enrichment_input.image_file_references[0].file_content=None
                    
                    if response.context.enrichment_input.text_file_references and len(response.context.enrichment_input.text_file_references) > 0:        
                        response.context.enrichment_input.text_file_references[0].file_content=None
                    
                self._logger.info(f"{ELC.AI_ENRICHMENT_PROCESS_TRANSFORMATION_COMPLETED_INFO.format(inputs_count=len(raw_responses),processed_count=len(transformed_responses))}")
            
                self._save(self.enrichment_generation_id, transformed_responses)
            return n_active_contexts

        except Exception:
            raise


    def _run_distributed_mode(self,  input_df: pyspark.sql.DataFrame) -> int:
        """ Distributed mode processing of the enrichment input and saves the transformed enriched response.

        Args:
            input_df (pyspark.sql.DataFrame): The input dataframe for the enrichment process.
        
        Returns:
            int: The number of active enrichment contexts processed.
        """
        enriched_df = self._run_model_processing_and_transformation(input_df)
        if not enriched_df:
            return 0
        n_rows = enriched_df.count()
        self._logger.info(ELC.AI_ENRICHMENT_EXECUTE_STARTED_INFO.format(inputs_count=n_rows, generation_id= self.enrichment_generation_id))
        n_partitions = enriched_df.rdd.getNumPartitions()
        if n_rows // n_partitions > self.enrichment_output_records_limit_per_file:
            n_partitions = max(1, n_rows // self.enrichment_output_records_limit_per_file)
            n_partitions = max(n_partitions, self.partition_config[EC.ENRICHMENT_SAVE_PARTITION])
            # assume equi-distribution....if equal no need to repartition
            if enriched_df.rdd.getNumPartitions() != n_partitions:
                enriched_df = enriched_df.repartition(n_partitions)
                self._logger.info(ELC.AI_ENRICHMENT_ENRICHMENT_EXECUTION_REPARTITION.format(n_partitions=n_partitions))

        g_id, root, is_json = self.enrichment_generation_id, self.storage_path, (self.output_format == "json")
        ext = "json" if is_json else GC.DEFAULT_FHIR_NDJSON_FILE_EXTENSION

        def process_partition(iterator):
            partition_id = TaskContext.get().partitionId()
            results = [EnrichmentResult(**json.loads(row.enrichment_results)) for row in iterator if row.enrichment_results]
            file_info = []
            for o_type in {o.type.lower() for r in results for o in r.outputs}:
                out_path = os.path.join(root, AIEnrichmentsUtils.format_output_type_for_output_path(o_type), EC.ENRICHMENT_LANDING_ZONE_DIR)
                sub_results = [r.model_copy(update={"outputs": [o for o in r.outputs if o.type.lower() == o_type]})
                               for r in results if any(o.type.lower() == o_type for o in r.outputs)]
                content = '\n'.join(json.dumps(r.to_dict(), separators=(',', ':')) for r in sub_results)
                if is_json:
                    file_info += [{"file_path": os.path.join(out_path, f"{g_id}_{partition_id}_{uuid.uuid4()}.{ext}"), "file_content": line}
                                  for line in content.splitlines() if line]
                else:
                    file_info.append({"file_path": os.path.join(out_path, f"{g_id}_{partition_id}_{uuid.uuid4()}.{ext}"), "file_content": content})
            return iter(file_info)

        for f in enriched_df.rdd.mapPartitions(process_partition).collect():
            self.mssparkutils_client.fs_put(f["file_path"], f["file_content"], overwrite=True)

        return n_rows
    
    
    def _initialize_paths(self) -> None:
        """
        Initialize file and storage paths for the enrichment process.
        """
        self.files_path = FolderPath.get_fabric_files_path(
            workspace_name=self.workspace_name,
            one_lake_endpoint=self.one_lake_endpoint,
            lakehouse_name=self.landing_zone_lakehouse_id,
        )
        
        ai_enrichment_landing_zone_path = self.parameter_service.get_activity_config_value(
                    EC.DEFAULT_AI_ENRICHMENT_LANDING_ZONE_PATH_KEY,
                    EC.ENRICHMENT_LANDING_ZONE_PATH)
        
        self.storage_path= f"{self.files_path}/{ai_enrichment_landing_zone_path}"  
        
        self.source_lakehouse_name=self.mssparkutils_client.get_lakehouse(self.silver_lakehouse_id).get("displayName")
        

    def _process_batch_contexts(self, batch: List[Dict]) -> List[EnrichmentContext]:
        """ 
        Process a batch of records and return the enrichment input contexts.

        Args:
            batch (List[Dict]): The batch of records to process.
        Returns:
            List[EnrichmentContext]: The list of enrichment input contexts for the batch.
        """
        curr_enrichment_input_contexts = []  
        for record in batch:  
            curr_enrichment_input_context = self._contextualize_record_for_enrichment(record)  
            if curr_enrichment_input_context:  
                curr_enrichment_input_contexts.append(curr_enrichment_input_context)  
        return curr_enrichment_input_contexts 
    

    def _construct_active_enrichment_contexts(self, input_records_to_process: List[Dict], batch_size: int = 10) -> List[EnrichmentContext]:  
        """  
        Construct the active enrichment contexts from the input records to process. Active means that the   
        enrichment context is not previously processed.  
    
        Args:  
            input_records_to_process (List[Dict]): The list of input records to process.
            batch_size (int): The size of each batch for processing. Default is 10.  
    
        Returns:  
            List[EnrichmentContext]: The list of prepared enrichment contexts.  
    
        Raises:  
            Exception: If any error occurs during the preparation of enrichment inputs.  
        """

        try:  
            enrichment_input_contexts = []  
  
            if len(input_records_to_process) > 0:  
                # Split the records into batches  
                batches = [input_records_to_process[i:i + batch_size] for i in range(0, len(input_records_to_process), batch_size)]  
                
                with ThreadPoolExecutor(max_workers=self.execution_threads) as executor:  
                    # Process each batch in parallel  
                    futures = {executor.submit(self._process_batch_contexts, batch): batch for batch in batches}  
                    
                    for future in as_completed(futures):  
                        batch_result = future.result()  
                        enrichment_input_contexts.extend(batch_result) 
                
                enrichment_context_ids = {context.enrichment_context_id for context in enrichment_input_contexts}
                alread_avail_enrichment_contexts = set(self.enrichment_metadata_service.get_active_context_ids(list(enrichment_context_ids)))  
                latest_input_contexts = enrichment_context_ids - alread_avail_enrichment_contexts  
                enrichment_input_contexts = [context for context in enrichment_input_contexts if context.enrichment_context_id in latest_input_contexts]  
    
                return enrichment_input_contexts      
            
        except Exception:  
            raise   
            
    def _setup_enrichment_metadata(self, enrichment_id: str) -> None:
        """
        Set up the enrichment metadata for the enrichment process.
        Args:
            enrichment_id (str): The ID of the enrichment process.
        Raises:
            ExecutionServiceError: If any error occurs during the setup of enrichment metadata.
        Returns:
            None
        """
        self.enrichment_definition_id = enrichment_id
        self.enrichment_generation_id = str(uuid.uuid4())
        enrichment_info = self.enrichment_metadata_service.get_enrichment_info(enrichment_id)
        if not enrichment_info:
            raise ExecutionServiceError(EC.ENRICHMENT_DEFINITION_NOT_FOUND.format(enrichment_id=enrichment_id))
        self.enrichment_definition = enrichment_info.definition
        self.enrichment_definition.input_mapping.metadata = json.loads(self.enrichment_definition.input_mapping.metadata)
        view_id = self.enrichment_definition.view_id
        if not view_id:
            raise ExecutionServiceError(EC.ENRICHMENT_VIEW_ID_NOT_FOUND.format(view_id=enrichment_id))
        self.enrichment_definition.model = json.loads(enrichment_info.definition.model)
        enrichment_view_info = self.enrichment_metadata_service.get_enrichment_view_info(view_id)
        if not enrichment_view_info:
            raise ExecutionServiceError(EC.ENRICHMENT_VIEW_INFO_NOT_FOUND.format(view_id=view_id))
        self.enrichment_view_info = enrichment_view_info
        self.model_config = self._get_model_configuration(self.enrichment_definition.model)
        AIEnrichmentsUtils.validate_model_config(self.model_config)
        AIEnrichmentsUtils.validate_input_mapping(self.enrichment_definition.input_mapping, self.enrichment_definition_id)
        
    def _run_enrichment_definition(self) -> pyspark.sql.DataFrame:
        """
        Executes the enrichment definition to construct the dataframe from the given view ID and
        respective SQL query expression.
        Args:
            enrichment_id (str): The ID of the enrichment process.

        Returns:
            pyspark.sql.DataFrame: The input dataframe for the enrichment process.
        """
        try:
            sql_query = self._prepare_sql_query(self.enrichment_view_info)
            self._logger.info(sql_query)
            input_df = self.spark.sql(sql_query)
            if input_df.count() > 0:
                # save materialized view. 
                # yet to do:- good for tracing, however, depending on perf observation, optimize.
                self._get_materialized_view_path(self.enrichment_view_info, input_df)
            return input_df
        except Exception:
            raise


    def _get_model_configuration(self, model_configuration: dict) -> Dict:
        """
        Get the model configuration from the enrichment definition.

        Args:
            model_configuration (dict): The model configuration.

        Raises:
            ModelConfigurationError: If the model configuration is not found or an unexpected error occurs.
        """
        if not model_configuration:
            raise ModelConfigurationError(EC.ENRICHMENT_MODEL_CONFIGURATION_INVALID)

        api_key_secret_identifier = model_configuration.get(EC.ENRICHMENT_API_SECRET_KEY_NAME)
        if api_key_secret_identifier:
            try:
                kv_uri = model_configuration.get(EC.ENRICHMENT_API_KV_KEY_NAME) or FolderPath.get_key_vault_uri(self.kv_name)
                api_key = self.mssparkutils_client.credentials_getSecret(kv_uri, api_key_secret_identifier)
                model_configuration["api_key"] = api_key
            except Exception as e:
                raise ModelConfigurationError(EC.ENRICHMENT_UNEXPECTED_ERROR.format(method="_get_model_configuration", error=e))  
        return model_configuration
        

    def _run_model_processing_and_transformation(self, input_df: pyspark.sql.DataFrame) -> Union[pyspark.sql.DataFrame, None]:
        """
        Processes the enrichment input and returns the transformed enriched response using a vectorized UDF.

        Args:
            enrichment_input_contexts_list (List[EnrichmentContext]): The list of input contexts for the enrichment process.

        Returns:
            List[EnrichmentResult]: The enriched response after processing.
        """
        try:
            process_batch = self._define_process_batch_transformation()

            enriched_rdd = None
            batch_index = 0
            batch_size = self.enrichment_collect_batch_size
            running_sum_active_contexts = 0
            n_records = input_df.rdd.count()
            n_rem_contexts = n_records
            for i in range(0, n_records, batch_size):
                # check if we have reached the limit of needed n_records to process.
                if self.enrichment_records_limit > 0:
                    n_rem_contexts = self.enrichment_records_limit - running_sum_active_contexts
                    if n_rem_contexts <= 0:
                        break

                batch_index += 1 
                self._logger.info(f"Enriching batch: {batch_index}")
                # Take a batch from the RDD  
                batch_rdd = input_df.rdd.zipWithIndex().filter(lambda x: i <= x[1] < i + batch_size).keys()  
                input_records_to_process = [row.asDict() for row in batch_rdd.collect()]
                enrichment_input_contexts_list = self._construct_active_enrichment_contexts(input_records_to_process)

                if self.enrichment_records_limit > 0:
                    enrichment_input_contexts_list = enrichment_input_contexts_list[:n_rem_contexts]
                    running_sum_active_contexts += len(enrichment_input_contexts_list)

                if len(enrichment_input_contexts_list) > 0:
                    new_rows = [Row(enrichment_context=json.dumps(context.to_dict())) for context in enrichment_input_contexts_list]
                    # Parallelize the list to create a new RDD  
                    rdd_with_content = self.spark.sparkContext.parallelize(new_rows, numSlices=self.partition_config[EC.ENRICHMENT_EXECUTION_PARTITION])
                    batch_results = rdd_with_content.mapPartitions(process_batch)  
                    if not enriched_rdd:
                        enriched_rdd = self.spark.sparkContext.emptyRDD()
                    enriched_rdd = enriched_rdd.union(batch_results)

            if not enriched_rdd:
                return None
            enriched_df = enriched_rdd.toDF(["enrichment_context_id", "enrichment_results"])  
            return enriched_df

        except Exception as e:
            raise ExecutionServiceError(e) from e


    def _define_process_batch_transformation(self):
        """
        Defines the batch transformation function for processing enrichment data.

        Returns:
            function: The defined batch transformation function.
        """
        enrichment_model_processor_instance = self.enrichment_model_processor
        enrichment_model_transformer_instance = self.enrichment_transformer
        model_config_data = self.model_config
        enrichment_generation_id = self.enrichment_generation_id
        enrichment_definition_id = self.enrichment_definition_id
        logger_name=self.__class__.__name__
  

        def process_batch(batch: Iterable) -> List[Tuple]:
            _logger = WorkerExecutionLogger(logger_name, log_level=logging.DEBUG)
                        
            enrichment_context_data_series = [row.enrichment_context for row in batch]
            results = []
            if len(enrichment_context_data_series) > 0:
                _logger.info(f"Processing {len(enrichment_context_data_series)} records")
                enrichment_contexts = []
                for context_data in enrichment_context_data_series:
                    enrichment_contexts.append(EnrichmentContext(**json.loads(context_data)))


                raw_responses = enrichment_model_processor_instance.process(
                    enrichment_generation_id, model_config_data, enrichment_contexts
                )
                
                if len(raw_responses) == 0:
                    raise ExecutionServiceError(ELC.AI_ENRICHMENT_MODEL_PROCESS_EMPTY_RESPONSE_ERROR)
                
                transformed_responses: List[EnrichmentResult] = enrichment_model_transformer_instance.transform(
                    enrichment_generation_id, enrichment_contexts, raw_responses
                )

                if len(transformed_responses) == 0:
                    _logger.info(ELC.AI_ENRICHMENT_TRANSFORMATION_RECORDS_INFO.format(records_count=len(transformed_responses)))
                    
                for response in transformed_responses:
                    response.enrichment_definition_id = enrichment_definition_id
                    if response.context.enrichment_input.image_file_references and len(response.context.enrichment_input.image_file_references) > 0:
                            response.context.enrichment_input.image_file_references[0].file_content = None
                    if response.context.enrichment_input.text_file_references and len(response.context.enrichment_input.text_file_references) > 0:
                            response.context.enrichment_input.text_file_references[0].file_content = None
                
                for enrichment_result in transformed_responses:
                    enrichment_response = json.dumps(enrichment_result.to_dict())
                    results.append({
                        "enrichment_context_id": enrichment_result.context.enrichment_context_id,
                        "enrichment_results": enrichment_response
                    })
                
                _logger.info(f"Processed {len(transformed_responses)} records")
            return iter(results)
        
        return process_batch
    
    
    def _prepare_sql_query(self, enrichment_view_info: EnrichmentView) -> str:
        """
        Prepares the SQL query for fetching enrichment data.

        Args:
            enrichment_view_info (EnrichmentView): The enrichment view information.

        Returns:
            str: The prepared SQL query.

        Raises:
            Exception: If any error occurs during the preparation of the SQL query.
        """
        try:
            enrichment_view_definition = enrichment_view_info.definition
            sql_query = AIEnrichmentsUtils.extract_sql_query(enrichment_view_info, enrichment_view_definition)
            parent_ids = enrichment_view_definition.parent_views_ids

            if not AIEnrichmentsUtils.validate_views_in_sql_expression(sql_query, len(parent_ids)):
                raise ExecutionServiceError(EC.ENRICHMENT_SQL_QUERY_INVALID.format(enrichment_view_info_id=enrichment_view_info.id))

            references_paths = self._get_or_create_references_paths(parent_ids)
            return AIEnrichmentsUtils.replace_materialized_view_names(self.spark,sql_query, references_paths)

        except Exception:
            raise
        
    def _contextualize_record_for_enrichment(self, record: Dict[str, Any]) -> Optional[EnrichmentContext]:
        """
        Transforms record data into an EnrichmentContext object.

        Args:
            record (Dict[str, Any]): The record data

        Returns:
            Optional[EnrichmentContext]: The created EnrichmentContext object, or None if no valid context is created.
        """
        model_configuration = self.model_config
        input_mapping = self.enrichment_definition.input_mapping
        patient_id = input_mapping.patient_id
        meta_data = {key: record.get(column_name) for key, column_name in input_mapping.metadata.items()}
        text_resource_references_data = [
            ResourceReference(
                id=record.get(ref.id),
                content=record.get(ref.content),
                file_content=self.validate_and_extract_file_content(record.get(ref.content))
            )
            for ref in input_mapping.text_resource_references
            if record.get(ref.content)
        ]
        image_resource_references_data = [
            ResourceReference(
                id=record.get(ref.id),
                content=record.get(ref.content),
                file_content=self.validate_and_extract_file_content(record.get(ref.content))
            )
            for ref in input_mapping.image_resource_references
            if record.get(ref.content)
        ]

        updated_model_configuration = self._remove_excluded_keys(model_configuration)
        
        if text_resource_references_data or image_resource_references_data:
            enrichment_input = EnrichmentInput(
                patient_id=record.get(patient_id),
                metadata=meta_data,
                text_file_references=text_resource_references_data,
                image_file_references=image_resource_references_data
            )
            context = AIEnrichmentsUtils.create_context_string(
                updated_model_configuration,
                enrichment_input
            )
            context_id=AIEnrichmentsUtils.get_hash_id(context)
            return EnrichmentContext(
                enrichment_context_id=context_id,
                enrichment_input=enrichment_input,
                model_configuration=updated_model_configuration
            )
        return None
    
    def validate_and_extract_file_content(self, path: str) -> str:
        """
        Validate specific components of an abfss:// path.

        Args:
            path (str): The string to validate.

        Returns:
            bool: True if all components are valid, False otherwise.
        """
        if path.startswith("abfss://"):
            return self._extract_file_content(path)
        else:
            return path    
        
    def _extract_file_content(self, file_path: str) -> str:
        """
        Return the appropriate file content based on file type.

        Args:
            file_path (str): Path to the file to be processed.

        Returns:
            bytes: The content of the file.
        """
        content=""
        if file_path.endswith(".zip"):
              content=self._extract_zip_content(file_path)
        else:
              content=self._extract_image_content(file_path)
        text_data=base64.b64encode(gzip.compress(content)).decode("utf-8")  
        return text_data    

    def _extract_zip_content(self, file_path: str) -> bytes:
        """
        Extract and return the content of the first file in the zip archive.

        Args:
            file_path (str): Path to the zip file to be processed.

        Returns:
            bytes: The content of the first file in the zip archive.
        """
        def _unzip_data(data: bytes) -> bytes:
            with zipfile.ZipFile(io.BytesIO(data), "r") as z:
                return z.read(z.namelist()[0])

        return (
            self.spark.sparkContext.binaryFiles(file_path)
            .map(lambda x: _unzip_data(x[1]))
            .collect()[0]
        )
    
        
    def _extract_image_content(self, file_path: str) -> bytes:
        """
        Load and return the content of a single image file.

        Args:
            file_path (str): Path to the image file to be processed.

        Returns:
            bytes: The content of the image file.
        """
        binary_df = self.spark.read.format("binaryFile").load(file_path)
        return binary_df.collect()[0].content
    
    def _remove_excluded_keys(self, model_configuration: dict) -> dict:
        """
        Removes any keys that are listed in the exclusion configuration from the given model configuration.

        This function uses the comma-separated keys defined in the enrichment model configuration's
        exclusion settings and filters them out from the provided dictionary.

        Args:
            model_configuration (dict):
                The dictionary containing model configuration data.

        Returns:
            dict:
                A new dictionary with all excluded keys removed, preserving only the allowed keys.

        """
        exclude_keys = [key.strip() for key in self.enrichment_model_defintion_excluded_keys.split(',')]
        return {k: v for k, v in model_configuration.items() if k not in exclude_keys}
        
    def _get_or_create_references_paths(self, parent_ids: List[str]) -> List[str]:
        """
        Retrieves the reference table paths for the parent views.

        Args:
            parent_ids (List[str]): The list of parent view IDs.

        Returns:
            List[str]: The list of reference paths.

        Raises:
            Exception: If any error occurs during the retrieval of reference paths.
        """
        references_paths = {}
        view_definitions = {parent_id: self.enrichment_metadata_service.get_enrichment_view_info(parent_id) for parent_id in parent_ids}

        for view_definition in view_definitions.values():
            parent_view_definition = view_definition.definition
            parent_view_ids = parent_view_definition.parent_views_ids
            if not parent_view_ids:
                references_paths[view_definition.name] = self.source_lakehouse_name
            else:
                sql_query = AIEnrichmentsUtils.extract_sql_query(view_definition, parent_view_definition)
                parent_references_paths = self._get_or_create_references_paths(parent_view_ids)
                sql_query = AIEnrichmentsUtils.replace_materialized_view_names(self.spark,sql_query, parent_references_paths)
                result_df = self.spark.sql(sql_query)
                materialized_view_path = self._get_materialized_view_path(view_definition, result_df)
                references_paths[materialized_view_path] = None
        return references_paths
    
    def _get_materialized_view_path(self, enrichment_view_info: EnrichmentView, result_df: pyspark.sql.DataFrame) -> str:
        """
        Creates materialized records for the given enrichment ID and view information.

        Args:
            enrichment_view_info (EnrichmentView): The enrichment view information.
            result_df (DataFrame): The result DataFrame.

        Returns:
            str: The name of the input table.
        """
        input_table_name = f"{EC.ENRICHMENT_MATERIALIZED_FILE_PREFIX}-{uuid.uuid4().hex}"
        target_table_path = f"{FolderPath.get_fabric_files_path(self.workspace_name, self.one_lake_endpoint, self.metadata_lakehouse_id)}/{EC.ENRICHMENT_MATERIALIZED_VIEWS_PATH}/{input_table_name}"
        result_df.write.format("delta").mode("overwrite").save(target_table_path)
        self.materialized_id = self.enrichment_metadata_service.create_materialized_view(enrichment_view_info, target_table_path)
        self.input_table_name = input_table_name
        return target_table_path

    def _save(self, enrichment_generation_id: str, enrichment_results: List[EnrichmentResult]) -> None:
            """
            Save the enrichment results to the storage path in batches.   Args:
            enrichment_generation_id (str): The ID of the enrichment generation.
            enrichment_results (List[EnrichmentResult]): The list of enrichment results to save.
        """
            os.makedirs(self.storage_path, exist_ok=True)
            unique_output_types = {output.type.lower() for result in enrichment_results for output in result.outputs}

            for output_type in unique_output_types:
                try:
                    self._process_output_type(output_type, enrichment_results, enrichment_generation_id)
                except Exception as e:
                    self._logger.error(EC.ENRICHMENT_UNEXPECTED_ERROR.format(method="save", error=e))

    def _process_output_type(self, output_type: str, enrichment_results: List[EnrichmentResult], enrichment_generation_id: str) -> None:
        self._logger.info(f"Processing output type: {output_type}")
        batch_size = self.enrichment_output_records_limit_per_file
        output_type_path = os.path.join(
            self.storage_path,
            AIEnrichmentsUtils.format_output_type_for_output_path(output_type),
            EC.ENRICHMENT_LANDING_ZONE_DIR
        )
        os.makedirs(output_type_path, exist_ok=True)

        results_by_output_type = [
            result.model_copy(update={"outputs": [output for output in result.outputs if output.type.lower() == output_type]})
            for result in enrichment_results
            if any(output.type.lower() == output_type for output in result.outputs)
        ]

        with ThreadPoolExecutor(max_workers=self.execution_threads) as executor:
            batch_index = 0
            for i in range(0, len(results_by_output_type), batch_size):
                batch_index += 1
                executor.submit(
                    self.save_batch_results,
                    results_by_output_type[i:i + batch_size],
                    batch_index,
                    output_type_path,
                    enrichment_generation_id,
                    self.output_format == "json"
                )
                
    def save_batch_results(self, batch_results:List[EnrichmentResult], batch_number, output_type_path, enrichment_generation_id, is_json):
            """
            Save the batch results to the specified output path.

            Args:
                batch_results (list): List of results to be saved.
                batch_number (int): The batch number for the current set of results.
                output_type_path (str): The path where the output files should be saved.
                enrichment_generation_id (str): The ID for the enrichment generation.
                is_json (bool): Flag indicating whether the output should be in JSON format.

            Returns:
                None
            """
            
            if len(batch_results) == 0:
                return
            
            file_extension = "json" if is_json else GC.DEFAULT_FHIR_NDJSON_FILE_EXTENSION
            file_content = '\n'.join(json.dumps(result.to_dict(), separators=(',', ':')) for result in batch_results)
        
            final_output_path = ""
            if is_json:
                for line in file_content.splitlines():
                    if line:
                        final_output_path = os.path.join(output_type_path, f"{enrichment_generation_id}_{uuid.uuid4()}.json")
                        self.mssparkutils_client.fs_put(final_output_path, line, overwrite=True)
            else:
                final_output_path = os.path.join(output_type_path, f"{enrichment_generation_id}_{uuid.uuid4()}.{file_extension}")
                self.mssparkutils_client.fs_put(final_output_path, file_content, overwrite=True)
        
            self._logger.info(f"{EC.ENRICHMENT_OUTPUT_SAVE_INFO.format(batch_number=batch_number, final_output_path=final_output_path)}")