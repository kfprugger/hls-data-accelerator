# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------

import json
from typing import Any, Dict, List, Optional

import concurrent
import uuid
from pyspark.sql import SparkSession, DataFrame
from microsoft.fabric.hls.hds.ai_enrichments.core.errors.metadata_service_error import MetaDataServiceError
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.metadata.enrichment import (
    Enrichment,
)
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.metadata.enrichment_definition import EnrichmentDefinition
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.metadata.enrichment_materialized_view import (
    EnrichmentMaterializedView,
)
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.metadata.enrichment_view import (
    EnrichmentView,
)
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.metadata.enrichment_view_definition import EnrichmentViewDefinition
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.metadata.enrichment_view_expression import EnrichmentViewExpression
from microsoft.fabric.hls.hds.ai_enrichments.core.models.enrichment.metadata.generated_enrichment import (
    GeneratedEnrichment,
)
from microsoft.fabric.hls.hds.services.delta_table_service import DeltaTableService
from microsoft.fabric.hls.hds.utils.dataframe_utils import get_record
from microsoft.fabric.hls.hds.utils.logging_helper import LoggingHelper
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import (
    MSSparkUtilsClientBase,
)
from microsoft.fabric.hls.hds.utils.parameter_service import ParameterService
from microsoft.fabric.hls.hds.utils.utils import FolderPath, Utils
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_logging_constants import AIEnrichmentsLoggingConstants as LC
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_constants import (
    AIEnrichmentsConstants as EC,
)
from microsoft.fabric.hls.hds.ai_enrichments.core.repository.metadata_repository_lakehouse_storage import (
    MetadataRepositoryLakehouseStorage,
)
from microsoft.fabric.hls.hds.global_constants.global_constants import (
    GlobalConstants as GC,
)

class AIEnrichmentsMetaDataService:
    def __init__(
        self,
        spark: SparkSession,
        workspace_name: str,
        solution_name: str,
        admin_lakehouse_name: str,
        one_lake_endpoint: str = GC.DEFAULT_ONE_LAKE_ENDPOINT,
        inline_params: Optional[Dict[str, Any]] = None,
        mssparkutils_client: Optional[MSSparkUtilsClientBase] = None,
    ):
        """
        Initialize the AIEnrichmentsMetaDataService.

        Args:
            spark (SparkSession): The Spark session.
            workspace_name (str): The workspace name.
            solution_name (str): The solution name.
            admin_lakehouse_name (str): The admin lakehouse name.
            one_lake_endpoint (str, optional): The OneLake endpoint.
            inline_params (Optional[Dict[str, Any]], optional): Inline parameters.
            mssparkutils_client (Optional[MSSparkUtilsClientBase], optional): The MSSparkUtils client.
        """
        
        self.spark = spark
        self.workspace_name = workspace_name
        self.solution_name = solution_name
        self.mssparkutils_client = Utils.get_mssparkutils_client(mssparkutils_client)
        self.one_lake_endpoint = one_lake_endpoint
        
        self.parameter_service = ParameterService(
            spark=self.spark,
            workspace_name=workspace_name,
            admin_lakehouse_name=admin_lakehouse_name,
            one_lake_endpoint=self.one_lake_endpoint,
            mssparkutils_client=self.mssparkutils_client,
            inline_params=inline_params,
        )
        
        self.silver_database_name = self.parameter_service.get_foundation_config_value(GC.SILVER_LAKEHOUSE_ID_KEY)    

        self._logger = LoggingHelper.get_ai_enrichment_metadata__logger(
            self.spark, self.__class__.__name__, GC.LOGGING_LEVEL
        )
        
        self.meta_data_lakehouse_id = (self.parameter_service.get_foundation_config_value(EC.ENRICHMENT_METADATA_LAKEHOUSE_ID_KEY))
         
        self.meta_data_lakehouse_name =self.mssparkutils_client.get_lakehouse(self.meta_data_lakehouse_id).get("displayName")
        
        self.tables_path = self.parameter_service.get_activity_config_value(
                EC.ENRICHMENT_METADATA_STORE_PATH_KEY,
                FolderPath.get_fabric_tables_path(
                    self.workspace_name, 
                    self.one_lake_endpoint, 
                    self.meta_data_lakehouse_id
                )
        )
        
        self.target_tables_path = self.parameter_service.get_activity_config_value(
                EC.ENRICHMENT_METADATA_STORE_PATH_KEY,
                FolderPath.get_fabric_tables_path(
                    workspace_name=self.workspace_name,
                    one_lake_endpoint=self.one_lake_endpoint,
                    lakehouse_name=self.meta_data_lakehouse_id,
                ),
        )
        
        self.repository = MetadataRepositoryLakehouseStorage(
            spark=self.spark,
            tables_path=self.target_tables_path,
            logger=self._logger
        )
        
        if self.meta_data_lakehouse_name and self.meta_data_lakehouse_id:
            refresh_view_data = inline_params.get(EC.REFRESH_METADATA_KEY, False) if inline_params else False
            self._initialize_metadata_store(refresh_view_data)
        
        
    
    def _initialize_metadata_store(self, refresh_view_data: bool) -> None:
        """
        Initialize the metadata store.

        Args:
            refresh_view_data (bool): Flag indicating whether to refresh view data.
        """
        try:
            delta_table_service = DeltaTableService(self.spark)
            base_metadata_tables = [
                EC.ENRICHMENT_VIEW_TABLE,
                EC.ENRICHMENT_TABLE,
                EC.ENRICHMENT_CONTEXT_TABLE,
                EC.ENRICHMENT_MATERIALIZED_TABLE,
                EC.ENRICHMENT_GENERATED_INFO_TABLE
            ]
            meta_store_tables_not_exists = delta_table_service.check_if_table_exists(
                self.meta_data_lakehouse_name, base_metadata_tables
            )

            is_empty_metadata_store = len(meta_store_tables_not_exists) > 0

            if is_empty_metadata_store:
                self._create_metadata_tables()

            if refresh_view_data:
                self.refresh_metadata_store()
                
        except Exception as e:
            self._logger.error(LC.ERROR_INITIALIZING_METADATA_STORE.format(e))

    def refresh_metadata_store(self) -> None:
        """
        Refresh the metadata store by retrieving a list of tables from the silver database
        and verifying if they are present in the repository. If a table does not exist,
        create the corresponding enrichment view. This ensures that all silver tables
        have a matching enrichment view record within the repository.
        """
        silver_tables_set = {t.name for t in self.spark.catalog.listTables(self.silver_database_name)}
        existing_view_names = self.repository.get_active_records(
            silver_tables_set, EC.ENRICHMENT_VIEW_TABLE, "name"
        )
        missing_tables = silver_tables_set - existing_view_names
        for table_name in missing_tables:
            enrichment_view = EnrichmentView(
                name=table_name,
                description=f"View for {table_name}",
                definition=self._get_default_view_definition(),
            )
            self.create_enrichment_view(enrichment_view)

                
    def _create_metadata_tables(self) -> None:  
        """  
        Create all required metadata tables.  
        """  
        with concurrent.futures.ThreadPoolExecutor() as executor:  
            futures = [  
                executor.submit(self._create_table, EC.AI_ENRICHMENT_VIEW_SCHEMA, EC.ENRICHMENT_VIEW_TABLE),  
                executor.submit(self._create_table, EC.AI_ENRICHMENT_SCHEMA, EC.ENRICHMENT_TABLE),
                executor.submit(self._create_table, EC.AI_ENRICHMENT_CONTEXT_SCHEMA, EC.ENRICHMENT_CONTEXT_TABLE),  
                executor.submit(self._create_table, EC.AI_ENRICHMENT_MATERIALIZED_VIEW_SCHEMA, EC.ENRICHMENT_MATERIALIZED_TABLE),  
                executor.submit(self._create_table, EC.AI_ENRICHMENT_GENERATED_SCHEMA, EC.ENRICHMENT_GENERATED_INFO_TABLE),    
            ]  
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    self._logger.error(f"Error creating metadata tables: {e}")
    
    def _create_table(self, schema, table_name):  
        """  
        Create a table with the given schema and table name.  

        Parameters:  
        schema (StructType): The schema of the table.  
        table_name (str): The name of the table.  
        """  
        df = self.spark.createDataFrame(data=[], schema=schema)  
        df.write.format("delta").mode("overwrite").save(f"{self.tables_path}/{table_name}")  
        
    def _get_default_view_definition(self) -> EnrichmentViewDefinition:
        """
        Get the default view definition.

        Returns:
            str: The default view definition as a string.
        """
        
        return EnrichmentViewDefinition(
            expression=EnrichmentViewExpression()
        )
        
    # Enrichment View Methods
    def create_enrichment_view(self, view_definition: EnrichmentView) -> str:
        """ Create an enrichment view in the metadata store. If a view with the same 
            name and definition exissts, it will be reused. If a view with the same name
            but different definition exists, an error will be raised.
        """
        for parent_view_id in view_definition.definition.parent_views_ids:
            if not self.get_enrichment_view_info(parent_view_id):
                raise MetaDataServiceError(
                    EC.ENRICHMENT_VIEW_ID_NOT_FOUND.format(view_id=parent_view_id)
                )
        
        try:
            temp_ids = self.get_enrichment_view_ids([view_definition.name])
        except MetaDataServiceError as e:
            temp_ids = []
        if temp_ids:
            temp_id = temp_ids[0]
            temp_enrichment_view_info = self.get_enrichment_view_info(temp_id)
            if temp_enrichment_view_info == view_definition:
                self._logger.info(EC.ENRICHMENT_VIEW_USING_EXISTING_VIEW.format(view_id=temp_id))
                return temp_id
            else:
                raise MetaDataServiceError(EC.ENRICHMENT_VIEW_NAME_ALREADY_EXISTS.format(view_name=view_definition.name))
            
        
        return self.repository.create_record(
            EC.AI_ENRICHMENT_VIEW_SCHEMA,
            {
                "name": view_definition.name,
                "description": view_definition.description,
                "definition": json.dumps(view_definition.definition.to_dict()),
                "id": view_definition.id
            },
            EC.ENRICHMENT_VIEW_TABLE,
        )

    def delete_enrichment_view(self, view_id: str) -> None:
        self.repository.delete_record(EC.ENRICHMENT_VIEW_TABLE, view_id)
        self._logger.info(
            LC.ENRICHMENT_VIEW_DELETED.format(
                view_id, EC.ENRICHMENT_VIEW_TABLE
            )
        )

    def get_enrichment_view_info(self, view_id: str) -> Optional[EnrichmentView]:
        view_info:EnrichmentView= self.repository.get_record_info(
            view_id, EC.ENRICHMENT_VIEW_TABLE, EnrichmentView
        )
        if not view_info:
            self._logger.warning(LC.ENRICHMENT_VIEW_NOT_FOUND.format(view_id))
            return
        view_info.definition = EnrichmentViewDefinition(**json.loads(view_info.definition))
        return view_info
    
    def get_enrichment_view_ids(self, view_names: List[str]) -> List[str]:
        """
        Retrieve the IDs of enrichment views based on their names.

        Args:
            view_names (List[str]): A list of view names to retrieve IDs for.

        Returns:
            List[str]: A list of view IDs corresponding to the provided view names.

        Raises:
            MetaDataServiceError: If any of the view names are not found.
        """
        # Use list comprehension to retrieve view IDs
        view_ids = [
            self._get_view_id_by_name(name) for name in view_names
        ]
        return view_ids

    def _get_view_id_by_name(self, name: str) -> str:
        """
        Helper method to get the view ID by name.

        Args:
            name (str): The name of the view.

        Returns:
            str: The ID of the view.

        Raises:
            MetaDataServiceError: If the view name is not found.
        """
        view_info = self.repository.get_record_info(
            name, EC.ENRICHMENT_VIEW_TABLE, EnrichmentView,"name", 
        )
        if not view_info:
            raise MetaDataServiceError(LC.ENRICHMENT_VIEW_NOT_FOUND.format(name))
        return view_info.id


    # Enrichment Methods
    def create_enrichment(self, enrichment: Enrichment) -> str:
        if not self.get_enrichment_view_info(enrichment.definition.view_id):
                raise MetaDataServiceError(
                    EC.ENRICHMENT_VIEW_ID_NOT_FOUND.format(view_id=enrichment.definition.view_id)
                )
        return self.repository.create_record(
            EC.AI_ENRICHMENT_SCHEMA,
            {
                "name": enrichment.name,
                "description": enrichment.description,
                "definition": json.dumps(enrichment.definition.to_dict()),
                "id":enrichment.id
            },
            EC.ENRICHMENT_TABLE,
        )

    def delete_enrichment(self, enrichment_id: str) -> None:
        self.repository.delete_record(EC.ENRICHMENT_TABLE, enrichment_id)

    def get_enrichment_info(self, enrichment_id: str) -> Optional[Enrichment]:
        enrichment_info = self.repository.get_record_info(
            enrichment_id, EC.ENRICHMENT_TABLE, Enrichment
        )
        if not enrichment_info:
            self._logger.warning(LC.ENRICHMENT_NOT_FOUND.format(enrichment_id))
            return
        enrichment_info.definition = EnrichmentDefinition(**json.loads(enrichment_info.definition))
        return enrichment_info

    # Enrichment Materialized View Methods
    def create_materialized_view(
        self, enrichment_view_info: EnrichmentView, table_path: str
    ) -> str:
        materialized_view_id = self.repository.create_record(
            EC.AI_ENRICHMENT_MATERIALIZED_VIEW_SCHEMA,
            {
                "view_id": enrichment_view_info.id,
                "reference_materialized_view_path": table_path,
                "name": f"Materialized View for {enrichment_view_info.name}",
                "id":str(uuid.uuid4())
            },
            EC.ENRICHMENT_MATERIALIZED_TABLE,
        )
        return materialized_view_id

    def delete_materialized_view(self, materialized_view_id: str) -> None:
        self.repository.delete_record(
            EC.ENRICHMENT_MATERIALIZED_TABLE, materialized_view_id
        )
        self._logger.info(LC.MATERIALIZED_VIEW_DELETED.format(materialized_view_id))

    def get_enrichment_materialized_view_info(
        self, materialized_view_id: str
    ) -> Optional[EnrichmentMaterializedView]:
        materialized_view_info = self.repository.get_record_info(
            materialized_view_id,
            EC.ENRICHMENT_MATERIALIZED_TABLE,
            EnrichmentMaterializedView,
        )
        if not materialized_view_info:
            self._logger.warning(
                LC.MATERIALIZED_VIEW_NOT_FOUND.format(materialized_view_id)
            )
        return materialized_view_info

    # Generated Enrichment Methods
    def create_generated_enrichment(
        self, generated_enrichment: GeneratedEnrichment
    ) -> None:
        self.repository.create_record(
            EC.AI_ENRICHMENT_GENERATED_SCHEMA,
            {
                "materialize_view_id": generated_enrichment.materialize_view_id,
                "input_name": generated_enrichment.input_name,
                "name": generated_enrichment.name,
                "id":generated_enrichment.id
            },
            EC.ENRICHMENT_GENERATED_INFO_TABLE,
        )
        
    def _get_info(self, record_id: str, table_name: str, model_class: Any, column_name: str = 'id') -> Optional[Any]:
        """
        Retrieve record information from the specified Delta table.

        Args:
            record_id (str): The ID of the record.
            table_name (str): The name of the table.
            model_class (Any): The model class to map the record to.
            column_name (str): The column name to filter by. Defaults to 'id'.

        Returns:
            Optional[Any]: The record information, or None if not found.
        """
        try:
            record_info = get_record(self.spark, column_name, record_id, self.tables_path, table_name, model_class, self._logger)
            return record_info
        except Exception as e:
            raise MetaDataServiceError(LC.ERROR_RETRIEVING_RECORD_INFO.format(table_name, record_id, e)) from e

    
    def get_active_context_ids(self, context_ids: List[str]) -> Optional[set]:
            """
            Retrieve the current enrichment context IDs.

            Args:
                context_ids (List[str]): A list of context IDs to retrieve.

            Returns:
                Optional[set]: A set of current enrichment context IDs, or None if not found.
            """
            enrichment_context_results = self.repository.get_active_records(
                context_ids, EC.ENRICHMENT_CONTEXT_TABLE, EC.ENRICHMENT_CONTEXT_ID_COLUMN
            )
            return enrichment_context_results


    def save_enrichment_contexts(self, contexts_df: DataFrame) -> None:
        """
        Saves the provided enrichment contexts DataFrame to the EnrichmentContext table.
        Args:
            contexts_df (DataFrame): The DataFrame containing enrichment contexts to be saved.
        Returns:
            None
        """
        if contexts_df.count() == 0:
            self._logger.info("No contexts to save.")
            return
        
        # Write the DataFrame to the EnrichmentContext table
        self.repository.upsert_to_table(
            df=contexts_df,
            table_name= EC.ENRICHMENT_CONTEXT_TABLE,
            unique_columns= [EC.ENRICHMENT_CONTEXT_ID_COLUMN],
            source_modified_on_column= GC.DEFAULT_SILVER_MODIFIED_DATE_COL
            )