# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------

import json, uuid
from pyspark.sql.functions import (
    explode, from_json, col, collect_list
)
from pyspark.sql.types import StructType, StructField, StringType, TimestampType, ArrayType
from microsoft.fabric.hls.hds.sdoh.generate_dtt_configurations.generate_dtt_mapping import DTTMappingGenerator
from microsoft.fabric.hls.hds.sdoh.generate_dtt_configurations.sdoh_datatables_mapping import SDOHdataTablesMapping
from microsoft.fabric.hls.hds.sdoh.generate_dtt_configurations.sdoh_metadatatables_mapping import SDOHMetaDataTablesMapping
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants
from microsoft.fabric.hls.hds.utils.logging_helper import LoggingHelper
from microsoft.fabric.hls.hds.sdoh.bronze_ingestion.constants import SdohConstants
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.utils.utils import Utils as PlatformCommonUtil
import os

class DTTAdapterConfigurationGenerator:
    """
    A class used to process tables in a Spark database.

    ...

    Attributes
    ----------
    spark : SparkSession
        a SparkSession object to interact with the Spark cluster
    bronze_database_name : str
        the name of the database to process
    sdoh_config_file_path   
        Location of all the sdoh configuration files
    sdoh_table_prefix : str
        the prefix of the tables to process
    target_strings : list
        a list of target strings
    arrSDOHsourceToTargetMapping : list
        a list of mappings from source to target
    adapterContent : str
        a string of adapter content
    exclude_tables : list
        a list of tables to exclude from processing
    df_2 : DataFrame
        a DataFrame of the SdohLayout table
    tables : list
        a list of tables in the database
    processed_tables : list
        a list of tables to process
    json_structure : list
        a list to store the JSON structure
    json_array_dtt : list
        a list to store the DTT mapping

    Methods
    -------
    process_tables():
        Processes all the tables in the database that have the given prefix.
    process_table(df_1, table):
        Processes a single table.
    generate_queries(matching_array, location_array, lowest_unit, table):
        Generates SQL queries for a table.
    generate_dtt_metadata_mapping():
        Generates DTT mapping for a sdoh metadata tables.
    finalize():
        Completes the processing of DTT adapter configuration for all the sdoh tables and modifies the adapter content.
    """
    
    def __init__(self, 
                 spark, 
                 source_lakehouse_name, 
                 target_lakehouse_name, 
                 bronze_database_name,
                 sdoh_config_file_path,
                 adapterContent,
                 business_events_ingestion_service):
        
        self.spark = spark
        self._logger = LoggingHelper.get_sdoh_silveringestion_logger(
            self.spark, self.__class__.__name__, GlobalConstants.LOGGING_LEVEL
        )
        self.source_lakehouse_name=source_lakehouse_name,
        self.target_lakehouse_name=target_lakehouse_name,
        self.bronze_database_name = bronze_database_name
        self.sdoh_config_file_path = sdoh_config_file_path
        self.sdoh_table_prefix = SdohConstants.SD_PREFIX
        self.adapterContent = adapterContent
        self.tables = self.spark.sql(f"SHOW TABLES IN `{self.bronze_database_name}`").collect()
        self.processed_tables = spark.sql("SELECT DISTINCT datasetName FROM SdohDatasets")

        self.df_2 = (
            # First, parse individual layout JSONs
            self.spark.sql("""
                SELECT 
                    FROM_JSON(datasetLayout, 'STRUCT<
                        Category: STRING,
                        SubCategory: STRING,
                        SocialDeterminantName: STRING,
                        SocialDeterminantDescription: STRING,
                        HarmonizationKey: STRING,
                        Units: STRING,
                        createdDatetime: STRING,
                        LayoutID: STRING,
                        DataSetMetadataId: STRING
                    >') AS layout_obj
                FROM SdohDatasets
                WHERE datasetLayout IS NOT NULL
            """)
            # Extract DataSetMetadataId from the parsed JSON
            .withColumn("extracted_metadata_id", col("layout_obj.DataSetMetadataId"))
            # Group by the extracted ID
            .groupBy("extracted_metadata_id")
            .agg(collect_list("layout_obj").alias("datasetLayout"))
            # Explode these arrays to get individual layout rows
            .withColumn("datasetLayout", explode("datasetLayout"))
            .select("datasetLayout.*")
        )
     
        metadata_schema = ArrayType(StructType([
                StructField("DataSetName", StringType(), True),
                StructField("PublisherName", StringType(), True),
                StructField("PublishedDate", TimestampType(), True),
                StructField("ValidUntil", TimestampType(), True),
                StructField("DataSetMetadataId", StringType(), True),
                StructField("createdDatetime", TimestampType(), True),
                StructField("FolderPath", StringType(), True),
                StructField("LocationConfiguration", StringType(), True) 
            ]))            
        self.df_meta_data = (
                spark.sql("SELECT DISTINCT datasetMetadata FROM SdohDatasets")
                .withColumn("datasetMetadata", explode(from_json(col("datasetMetadata"), metadata_schema)))
                .select("datasetMetadata.*")  
            )

        self.json_structure=[]
        self.json_array_dtt = []
        self.business_events_ingestion_service= business_events_ingestion_service

   # Processes all the tables in the database that have the given prefix.
    def process_tables(self):
        # Generate DTT metadata mapping
        self.json_array_dtt = self.generate_dtt_metadata_mapping()
        # Process each table
        for row in self.processed_tables.collect():
            file_name=row.datasetName
    
            # Retrieve table data
            self._logger.info(LC.SDOH_TABLES_PROCESSING.format(
                        table_name=file_name)) 
            df_1 = self.spark.sql(f"SELECT * FROM SdohDatasets WHERE datasetName = '{file_name}'")
            distinct_ids = df_1.select("id").distinct().rdd.flatMap(lambda x: x).collect()
            
            for sheet_id in distinct_ids:
                df_sheet = df_1.filter(col("id") == sheet_id)
                self.process_table(df_sheet, file_name, sheet_id)
  
            self._logger.info(LC.SDOH_TABLES_PROCESSING_COMPLETED.format(
                        table_name=file_name)) 
            

    #Processes a single table.
    def process_table(self, df_1, file_name, sheet_id):
        
        location_columns=[]
        column_named_struct_parts = []
        link_to_socialdeterminant = None
        link_to_socialdeterminant_type = None
        
        # Get all JSON chunks
        chunks = df_1.select("datasetRowContent").collect()
        
        # Group chunks by source row ID
        row_chunks = {}
        for chunk in chunks:
            try:
                json_data = json.loads(chunk.datasetRowContent)
                
                # Extract the source row ID
                source_row_id = json_data.pop("row_id", None)
                
                if source_row_id is not None:
                    if source_row_id not in row_chunks:
                        row_chunks[source_row_id] = {}
                    
                    # Store this chunk's data
                    row_chunks[source_row_id].update(json_data)
            except Exception as e:
                self._logger.warning(f"Error parsing chunk in {file_name}: {str(e)}")
        
        json_obj = next(iter(row_chunks.values())) if row_chunks else {}
         
        df_1_columns_set = set(json_obj.keys())
        df_2_variable_codes_set = set(self.df_2.select("SocialDeterminantName").rdd.flatMap(lambda x: x).collect())
       
        
        # Find the common columns between df_1 and df_2
        metadata_schema = ArrayType(StructType([
                StructField("DataSetName", StringType(), True),
                StructField("PublisherName", StringType(), True),
                StructField("PublishedDate", TimestampType(), True),
                StructField("ValidUntil", TimestampType(), True),
                StructField("DataSetMetadataId", StringType(), True),
                StructField("createdDatetime", TimestampType(), True),
                StructField("FolderPath", StringType(), True),
                StructField("LocationConfiguration", StringType(), True) 
            ])) 
    
        df_exploded_meta = df_1.withColumn("datasetMetadata", explode(from_json(col("datasetMetadata"), metadata_schema)))

        dataset_id = df_exploded_meta.select("datasetMetadata.DataSetMetadataId").first()[0]

        matching_array = list(df_1_columns_set & df_2_variable_codes_set)

        all_keys = sorted(json_obj.keys())  # sort for consistency

        inner_struct = ", ".join([f"{col}:string" for col in all_keys])
        struct_string = f"'struct<{inner_struct}>'"
        if dataset_id:
            df_filtered_meta_data = self.df_meta_data.filter(self.df_meta_data.DataSetMetadataId == dataset_id)
            configurations=df_filtered_meta_data.select("LocationConfiguration").first()[0]
            if configurations:
                config = json.loads(configurations)
                for column in config:
                    if column[SdohConstants.LOC_CONFIG_COLUMN_NAME] in df_1_columns_set:
                        location_columns.append(f"{column[SdohConstants.LOC_CONFIG_COLUMN_NAME]}")
                        column_named_struct_parts.append(f"'{column[SdohConstants.LOC_CONFIG_STANDARD_COLUMN_NAME]}', dataColumns.{column[SdohConstants.LOC_CONFIG_COLUMN_NAME]}")
                # Find the columns in df_1 that are also in the target_strings list
                
                lowercase_target_strings = set(target.lower() for target in location_columns)
                location_array = list(lowercase_target_strings)
                location_array.sort()
                
                #location_array = location_columns
                for c in config:
                    if c[SdohConstants.LOC_CONFIG_ASSOCIATED_WITH_SDOH_VALUE] and c[SdohConstants.LOC_CONFIG_COLUMN_NAME] in df_1_columns_set:
                        link_to_socialdeterminant = c[SdohConstants.LOC_CONFIG_COLUMN_NAME]
                        link_to_socialdeterminant_type = c[SdohConstants.LOC_CONFIG_STANDARD_COLUMN_NAME]
                        break  # Pick the first encountered one
                # Generate queries using the matching_array, location_array, lowest_unit, and table
                self.generate_queries(matching_array, location_array, link_to_socialdeterminant, file_name,link_to_socialdeterminant_type,column_named_struct_parts,location_columns,struct_string, sheet_id)
            
            else:
                message = LC.SDOH_TABLES_LOCATION_CONFIGURATION_NOT_FOUND.format(table_name=file_name)
                self._logger.error(message)
                
                new_row = self.business_events_ingestion_service.create_new_business_event_row(id=str(uuid.uuid4()), activityName=GlobalConstants.SDOH_SILVER_INGESTION_ACTIVITY_NOTEBOOK, 
                    targetLakehouseName= self.target_lakehouse_name, targetTableName=SdohConstants.TABLE_SOCIAL_DETERMINANT,
                    sourceTableName=file_name, sourceLakehouseName= self.source_lakehouse_name, severity= GlobalConstants.ERROR, 
                    eventType= GlobalConstants.SDOH_PROCESS_TABLES_FROM_BRONZE_TO_SILVER, message= message, active=True)
                self.business_events_ingestion_service.insert_business_events([new_row])
                
                
        else:
            message = LC.SDOH_TABLES_DATASETMETADATAID_NOT_FOUND.format(table_name=file_name)
            self._logger.error(LC.SDOH_TABLES_DATASETMETADATAID_NOT_FOUND.format(
                        table_name=file_name))
            
            new_row = self.business_events_ingestion_service.create_new_business_event_row(id=str(uuid.uuid4()), activityName=GlobalConstants.SDOH_SILVER_INGESTION_ACTIVITY_NOTEBOOK, 
                targetLakehouseName= self.target_lakehouse_name, targetTableName=SdohConstants.TABLE_SOCIAL_DETERMINANT,
                sourceLakehouseName= self.source_lakehouse_name, severity= GlobalConstants.ERROR, 
                eventType= GlobalConstants.SDOH_PROCESS_TABLES_FROM_BRONZE_TO_SILVER, message= message, active=True)
            self.business_events_ingestion_service.insert_business_events([new_row])

    #Generates DTT mapping for a sdoh metadata tables.
    def generate_dtt_metadata_mapping(self):
        self._logger.info(LC.SDOH_TABLES_METADATA_DTT_MAPPING_PROCESSING)
        # Create an instance of SDOHMetaDataTablesMapping with the SDOH config file path
        sdoh_metadata_mapping = SDOHMetaDataTablesMapping(self.spark,f"{self.sdoh_config_file_path}/{GlobalConstants.SDOH_META_DATA_TABLES_MAPPING}")

        # Get the SDOH metadata mapping
        arr_sdoh_metadata = sdoh_metadata_mapping.get_mapping()

        # Define SQL queries for different metadata tables
        queries = {
            'SdohDataSetMetadata': f"""
                SELECT 
                    datasetMetadata.DataSetName AS Dataset_Name, 
                    datasetMetadata.PublisherName AS Publisher_Name, 
                    datasetMetadata.PublishedDate AS Published_Date, 
                    datasetMetadata.ValidUntil AS Valid_Until, 
                    datasetMetadata.{GlobalConstants.DEFAULT_BRONZE_CREATED_DATE_COL} as modifiedon, 
                    datasetMetadata.FolderPath AS FolderPath,
                    datasetMetadata.DataSetMetadataId AS Target_PK 
                FROM (
                    SELECT DISTINCT 
                        EXPLODE(from_json(datasetMetadata, 'ARRAY<STRUCT<
                            DataSetName: STRING, 
                            PublisherName: STRING, 
                            PublishedDate: STRING, 
                            ValidUntil: STRING, 
                            DataSetMetadataId: STRING,
                            createdDatetime: STRING,
                            FolderPath: STRING,
                            LocationConfiguration: STRING
                        >>')) AS datasetMetadata
                    FROM SdohDatasets
                ) 
                """,
            'SdohLayout_UOM': f"""
                SELECT DISTINCT 
                    layout_obj.Units, 
                    layout_obj.{GlobalConstants.DEFAULT_BRONZE_CREATED_DATE_COL} AS modifiedon, 
                    layout_obj.Units AS Target_PK 
                FROM (
                    SELECT 
                        FROM_JSON(datasetLayout, 'STRUCT<
                            Category: STRING,
                            SubCategory: STRING,
                            SocialDeterminantName: STRING,
                            SocialDeterminantDescription: STRING,
                            HarmonizationKey: STRING,
                            Units: STRING,
                            createdDatetime: STRING,
                            LayoutID: STRING,
                            DataSetMetadataId: STRING
                        >') AS layout_obj
                    FROM SdohDatasets
                    WHERE datasetLayout IS NOT NULL
                ) 
                WHERE layout_obj.Units IS NOT NULL
            """,
            'SdohLayout_Category': f"""
                SELECT 
                    layout_obj.Category AS Social_Determinant_Category_Name, 
                    layout_obj.Category AS Target_PK, 
                    layout_obj.{GlobalConstants.DEFAULT_BRONZE_CREATED_DATE_COL} AS modifiedon 
                FROM (
                    SELECT 
                        FROM_JSON(datasetLayout, 'STRUCT<
                            Category: STRING,
                            SubCategory: STRING,
                            SocialDeterminantName: STRING,
                            SocialDeterminantDescription: STRING,
                            HarmonizationKey: STRING,
                            Units: STRING,
                            createdDatetime: STRING,
                            LayoutID: STRING,
                            DataSetMetadataId: STRING
                        >') AS layout_obj
                    FROM SdohDatasets
                    WHERE datasetLayout IS NOT NULL
                ) 
                WHERE layout_obj.Category IS NOT NULL
            """,
            'SdohLayout_SubCategory': f"""
                SELECT DISTINCT
                    layout_obj.SubCategory AS Sub_Category, 
                    CONCAT_WS('', layout_obj.SubCategory, layout_obj.Category) AS Target_PK, 
                    layout_obj.Category AS Social_Determinant_Category_Id, 
                    layout_obj.{GlobalConstants.DEFAULT_BRONZE_CREATED_DATE_COL} AS modifiedon 
                FROM (
                    SELECT 
                        FROM_JSON(datasetLayout, 'STRUCT<
                            Category: STRING,
                            SubCategory: STRING,
                            SocialDeterminantName: STRING,
                            SocialDeterminantDescription: STRING,
                            HarmonizationKey: STRING,
                            Units: STRING,
                            createdDatetime: STRING,
                            LayoutID: STRING,
                            DataSetMetadataId: STRING
                        >') AS layout_obj
                    FROM SdohDatasets
                    WHERE datasetLayout IS NOT NULL
                ) 
                WHERE layout_obj.SubCategory IS NOT NULL AND layout_obj.Category IS NOT NULL
                """
        }

        # Create an instance of DTTMappingGenerator with the SDOH metadata and queries
        generate_dtt_mapping = DTTMappingGenerator(arr_sdoh_metadata, queries)
        
        self._logger.info(LC.SDOH_TABLES_METADATA_DTT_MAPPING_PROCESSED)

        # Generate the DTT mapping and return it as a list
        return list(generate_dtt_mapping.generate_dtt_mapping())

    #Generates SQL queries for a table.
    def generate_queries(self, matching_array, location_array, link_to_socialdeterminant, file_name,link_to_socialdeterminant_type,location_named_struct_parts,location_columns, struct_string, sheet_id):
        # Get SDOH data tables mapping
        self._logger.info(LC.SDOH_TABLES_DATA_DTT_MAPPING_PROCESSING)
        sdoh_mapping = SDOHdataTablesMapping(self.spark, f"{self.sdoh_config_file_path}/{GlobalConstants.SDOH_DATA_TABLES_MAPPING}")
        arr_sdoh_data = sdoh_mapping.get_mapping()

        sdoh_queries = dict()
        location_column_names_str = ", ".join(location_array)
        named_struct_str = ", ".join(location_named_struct_parts)
        aliased_columns = [f"dataColumns.{column}" for column in location_columns]
        location_aliased_columns = ", ".join(aliased_columns)
        sql_query_social_determinant = f"""SELECT s1.location_json AS Location_JSON_String, s1.location_value AS Location_Value, '{link_to_socialdeterminant_type}' AS Location_type, CONCAT_WS('', s1.row_id, s1.SocialDeterminantCode, m.DataSetMetadataId) AS Social_Determinant_Id, m.DataSetMetadataId AS DataSet_Metadata_Id, l.SocialDeterminantDescription AS Social_Determinant_Description, s1.SocialDeterminantCode AS Social_Determinant_Name, s1.SocialDeterminantValue AS Social_Determinant_Value, CONCAT_WS('', l.SubCategory, l.Category) AS Social_Determinant_SubCategory_Id, l.Units AS Unit_Of_Measure, l.HarmonizationKey AS Harmonization_Key, s1.ModifiedOn AS modifiedon FROM (SELECT id AS SdohDatasetId, layout_obj.Category, layout_obj.SubCategory, layout_obj.DataType, layout_obj.ColumnName, layout_obj.SocialDeterminantName, layout_obj.SocialDeterminantDescription, layout_obj.Units, layout_obj.DataSetMetadataId, layout_obj.HarmonizationKey FROM (SELECT id, FROM_JSON(datasetLayout, 'STRUCT<Category: STRING, SubCategory: STRING, DataType: STRING, ColumnName: STRING, SocialDeterminantName: STRING, SocialDeterminantDescription: STRING, DataSetMetadataId: STRING, Units: STRING, HarmonizationKey: STRING>') AS layout_obj FROM SdohDatasets WHERE datasetName = '{file_name}' AND datasetLayout IS NOT NULL)) l INNER JOIN (SELECT s.SocialDeterminantCode, s.SocialDeterminantValue, s.ModifiedOn, CONCAT_WS('',{location_column_names_str}) AS row_id, LocationType, s.location_json, s.location_value FROM (SELECT {location_aliased_columns}, TO_JSON(NAMED_STRUCT({named_struct_str})) AS location_json, sdohdata.createdDatetime AS ModifiedOn, dataColumns.{link_to_socialdeterminant} AS location_value, STACK({len(matching_array)}, {", ".join([f"dataColumns.{column} , '{column}'" for column in matching_array])}) AS (SocialDeterminantValue, SocialDeterminantCode) FROM (SELECT createdDatetime, FROM_JSON(combined_json, {struct_string}) AS dataColumns FROM (SELECT MAX(createdDatetime) AS createdDatetime, row_id, TO_JSON(MAP_FROM_ENTRIES(COLLECT_LIST(STRUCT(k, v)))) AS combined_json FROM (SELECT createdDatetime, CAST(GET_JSON_OBJECT(datasetRowContent, '$.row_id') AS STRING) AS row_id, EXPLODE(MAP_FILTER(FROM_JSON(datasetRowContent, 'MAP<STRING, STRING>'), (k, v) -> k != 'row_id')) AS (k, v) FROM SdohDatasets WHERE datasetName = '{file_name}' AND id = '{sheet_id}') GROUP BY row_id) aggregated_rows) sdohdata) s LATERAL VIEW EXPLODE(ARRAY({link_to_socialdeterminant})) exploded_table AS LocationType) s1 ON l.SocialDeterminantName = s1.SocialDeterminantCode INNER JOIN (SELECT DISTINCT id AS SdohDatasetId, metadata.DataSetMetadataId FROM (SELECT id, EXPLODE(FROM_JSON(datasetMetadata, 'ARRAY<STRUCT<DataSetMetadataId: STRING, DataSetName: STRING, PublisherName: STRING, PublishedDate: LONG, ValidUntil: STRING, createdDatetime: LONG, FolderPath: STRING, LocationConfiguration: STRING>>')) AS metadata FROM SdohDatasets WHERE datasetName = '{file_name}' AND id = '{sheet_id}' LIMIT 1) parsed) m ON l.DataSetMetadataId = m.DataSetMetadataId"""
        sdoh_queries['SocialDeterminant'] = sql_query_social_determinant
        
        # Generate DTT mapping
        sheet_name = sheet_id.split('_')[0]
        dataset_name= os.path.splitext(file_name)[0]
        if sheet_name:
            dataset_name = f"{dataset_name}_{sheet_name}"
        mapping_generator = DTTMappingGenerator(arr_sdoh_data, sdoh_queries, dataset_name)
        json_array_sdoh = mapping_generator.generate_dtt_mapping()
        self.json_array_dtt.extend(json_array_sdoh)
        self._logger.info(LC.SDOH_TABLES_DATA_DTT_MAPPING_PROCESSED)

    #Completes the processing of DTT adapter configuration for all the sdoh tables and modifies the adapter content.
    def finalize(self):
        # Process the tables
        self.process_tables()

        # Convert the JSON array to a string with indentation for readability
        json_output = json.dumps(self.json_array_dtt, indent=4)

        # Replace 'null' in the adapter content with the JSON output
        # This assumes that 'null' is a placeholder for the JSON output in the adapter content
        self.adapterContent = self.adapterContent.replace('null', json_output)

        # Return the updated adapter content
        return self.adapterContent