import uuid
import os
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.types import *
from pyspark.sql.functions import *
from microsoft.fabric.hls.hds.utils.logging_helper import LoggingHelper
import json
from datetime import datetime, timezone
from microsoft.fabric.hls.hds.utils.utils import Utils as CommonUtils
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.structured_stream.delta_table_stream_reader import DeltaTableStreamReader

class FHIRConverter:
    """
    This utility class is used to transform metadata from a Delta table 
    into a format compliant with FHIR resource specifications.
    """
    def __init__(self,
            fhir_resource: str,
            mapping_config: dict,
            spark_schema: StructType,
            source_modified_column_name: str = None) -> None:
    
        """
        Args:
        - fhir_resource (str): FHIR Resource for which utility methods are being used
        - mapping_config (dict): Configuration mapping for fhir transformations.
        - spark_schema (StructType): Spark DataFrame schema used to define the structure of the data.
        - source_modified_column_name (str): The name of the column indicating
          if the source data has been modified. Defaults to None.
        """
        
        self.fhir_resource = fhir_resource
        self.mapping_config = mapping_config
        self.spark_schema = spark_schema
        self.source_modified_column_name = source_modified_column_name
    
    def _df_groupby_and_agg(self, 
                           df: DataFrame, 
                           fhir_element_name: str, 
                           group_by_elements: dict,
                           ignore_elements: list = []) -> DataFrame:
        
        """
        This method is used to do appropriate grouping and aggregation based on parameters passed

        Args:
            - df (Dataframe): the dataframe to be processed
            - fhir_element_name (str): the fhir element on which grouping and aggregation needs to be done
            - ignore_elements (list, optional): list of elements which needs to be ignored while processing. Defaults to [].
        Returns:
            DataFrame: dataframe after group by and aggregation
        """    
            
        mapping = self.get_config_mappings(self.mapping_config, fhir_element_name)
        spark_schema = self.get_fhir_element_schema(self.spark_schema, fhir_element_name)
        
        #generate mapping expression for all the elements as defined in the mapping config
        mappings_expr = self._generate_mappings_expr(mapping, spark_schema, ignore_elements)
        
        # Add msftIsDeleted aggregation if the column exists in the source DataFrame
        if "msftIsDeleted" in df.columns:
            # For study level: check if ALL series are deleted
            if fhir_element_name in ["ImagingStudy", "series"]:
                mappings_expr.append("min(col('msftIsDeleted')).alias('msftIsDeleted')")  # True only if ALL are deleted
            # else:
            #     mappings_expr.append("max(col('msftIsDeleted')).alias('msftIsDeleted')")  # True if ANY are deleted           
        
        df_agg = df.groupBy(group_by_elements[fhir_element_name]).agg(
            *[eval(mapping_expr) for mapping_expr in mappings_expr]
        )
        
        for column, value in mapping.items():
            if not isinstance(value, list):
                #if its a 1:1 mapping as per mapping config, 
                #take the element which has max value for sourceModifiedAt field from the aggregated list
                #Example, say we do group by at series level and there are multiple modalities 
                #we take the value from the record which has max sourceModifiedAt
                df_agg = df_agg.withColumn(
                    column,
                    when(
                        col(column).isNotNull(),
                        array_max(column).getField('json_object')
                    ).otherwise(None))
            else:
                if column in GC.FHIR_EXTENDED_ELEMENTS or len(value)>1:
                    #this is a handling for special cases like 'identifier' fhir element 
                    #where it can have an array of different fhir structures/elements
                    #here also we try to take the value from the record having max sourceModifiedAt
                    df_agg = df_agg.withColumn(column, array_max(column).getField('json_object'))
                elif column not in ignore_elements:
                    #the object contains sourceModifiedAt as well as json_object fields
                    #extracting the json_object field (which is the actual fhir element)
                    # Check if the column is actually an array type before applying transform
                    column_schema = df_agg.schema[column].dataType
                    if isinstance(column_schema, ArrayType):
                        df_agg = df_agg.withColumn(column, expr(f"transform({column}, x -> x.json_object)"))
                    

        if "msftIsDeleted" in df_agg.columns:
            df_agg = self._add_soft_delete_extensions_post_agg(df_agg, fhir_element_name)
        
        #finally after all aggregations, we combine all the elements into a single struct 
        #named after the fhir element parameter passed  
        mapping_keys = [f"'{key}'" for key in mapping.keys()]
        
        # Add extension field to struct if it was added during soft-delete processing
        if "extension" in df_agg.columns and "extension" not in mapping.keys():
            mapping_keys.append("'extension'")
            
        df_agg = df_agg.withColumn(fhir_element_name, eval(f"struct({', '.join(mapping_keys)})"))
        
        df_agg = df_agg.select(*group_by_elements[fhir_element_name], fhir_element_name)
        return df_agg
        
    def get_ndjson_file_path(self,current_datetime: datetime, fhir_namespace: str) -> str:
        """
        This method is used to get the ndjson file path as per fhir landing zone contract

        Args:
            current_datetime (datetime): datetime for which ndjson needs to be stored
            fhir_namespace (str): namespace used in fhir landing zone contract

        Returns:
            str: path for storing fhir ndjson files
        """        
        ndjson_file_name = f"{self.fhir_resource}-{current_datetime.strftime(GC.FHIR_NDJSON_DATE_FORMAT)}{GC.FHIR_NDJSON_FILE_EXT}"
        
        year = str(current_datetime.year)
        month = current_datetime.strftime("%m")  # Zero-padded month
        day = current_datetime.strftime("%d") # Zero-padded day
        
        return os.path.join(fhir_namespace,
                            year, month, day,
                            ndjson_file_name)
    
    def get_config_mappings(self,mappings, fhir_element_name):
        """
        This method is used to get config mapping for a particular fhir element

        Args:
            mappings : config mapping object
            fhir_element_name : fhir element name

        Returns:
            mappings for the fhir elemenet
        """        
        if fhir_element_name == self.fhir_resource:
            return mappings
        
        mappings = mappings[fhir_element_name]
        if isinstance(mappings, list):
            mappings = mappings[0]
        return mappings
    
    def get_fhir_element_schema(self,schema, element):
        """
        This method is used to get schema definition for a particular fhir element

        Args:
            schema : spark schema definition object
            element : fhir element for which schema needs to be fetched

        Returns:
            spark schema for particular fhir element passed
        """        
        if element == self.fhir_resource:
            return schema
        
        if isinstance(schema, StructType):
            try:
                schema = schema[element].dataType
            except Exception as e:
                schema = StringType()
        if isinstance(schema, ArrayType):
            schema = schema.elementType
        
        return schema
        
   
    def _modify_expr_str_level_based(self, key: str, level: int, expr_str: str) -> str:
        """
        This method is used to modify expr string based on the nesting level

        Args:
            key (str): element key 
            level (int): nesting level
            expr_str (str): expression string

        Returns:
            str: modified expression string
        """    
            
        if level == 1:
            return(f"collect_set(struct(col('{self.source_modified_column_name}').alias('{self.source_modified_column_name}'), {expr_str}.alias('json_object'))).alias('{key}')")
        else:
            return(f"{expr_str}.alias('{key}')")
    
    def _add_soft_delete_extensions_post_agg(self, df_agg: DataFrame, fhir_element_name: str) -> DataFrame:
        """
        This method adds soft-delete extension at study, series, and instance levels based on msftIsDeleted status.        
        Study level: Add soft-delete extension if ALL series under that study are deleted
        Series level: Add soft-delete extension if ALL instances under that series are deleted  
        
        Args:
            df_agg (DataFrame): The aggregated dataframe
            fhir_element_name (str): The FHIR element name being processed
            
        Returns:
            DataFrame: DataFrame with soft-delete extensions added where applicable
        """ 
            
        # Define the soft-delete extension structure
        soft_delete_extension = struct(
            lit("http://azurehealthcareapis.com/data-extensions/deleted-state").alias("url"),
            lit("soft-deleted").alias("valueString")
        )        
        
        if fhir_element_name == "ImagingStudy":           
            df_agg = self._add_soft_delete_to_study_level(df_agg, soft_delete_extension)            
        elif fhir_element_name == "series":
            # Series level: Add extension if all instances are deleted            
            df_agg = self._add_soft_delete_to_series_level(df_agg, soft_delete_extension)  

        return df_agg
    
    def _add_soft_delete_to_study_level(self, df_agg: DataFrame, soft_delete_extension) -> DataFrame:
        """Add soft-delete extension to study level when all series are deleted"""
        # Check if we have an 'extension' column or if we need to create one
        if "extension" in df_agg.columns:
            return df_agg.withColumn(
                "extension",
                when(col("msftIsDeleted") == True,
                     # Add soft-delete extension to existing extensions
                     when(col("extension").isNotNull(),
                          array_union(col("extension"), array(soft_delete_extension))
                     ).otherwise(array(soft_delete_extension))
                ).otherwise(col("extension"))
            )
        else:
            # Create new extension column when msftIsDeleted is True
            return df_agg.withColumn(
                "extension",
                when(col("msftIsDeleted") == True, array(soft_delete_extension)).otherwise(lit(None))
            )
    
    def _add_soft_delete_to_series_level(self, df_agg: DataFrame, soft_delete_extension) -> DataFrame:
        """Add soft-delete extension to series level when all instances are deleted"""
        # At series level, the extension field doesn't exist in the mapping configuration
        # We need to add it as a new field when all instances in the series are deleted
        return df_agg.withColumn(
            "extension",
            when(col("msftIsDeleted") == True, array(soft_delete_extension)).otherwise(lit(None))
        )
        
    def _generate_mappings_expr(self, mapping: dict, spark_schema: StructType, ignore_elements:list=[], level: int =1) -> list:
            """
            This method is used recursively to generate pyspark expressions for aggregations 
            based on mapping config passed

            Args:
                mapping (dict): mapping dictionary for which expressions need to be generated
                spark_schema (StructType): spark schema
                ignore_elements (list, optional): list of elements to be ignored while generating expressions. Defaults to [].
                level (int, optional): nesting level. Defaults to 1.

            Returns:
                list: list of pyspark expression strings
            """        
            mappings_expr = []
            
            for key, value in mapping.items(): 

                if key in ignore_elements:
                    mappings_expr.append(f"collect_set(col('{key}')).alias('{key}')")
                    continue
                
                schema_for_key = self.get_fhir_element_schema(spark_schema, key)
                
                if isinstance(value, dict):
                    #if element value is of type dict then recursively call this method 
                    # to generate expression for nested elements as well
                    child_mappings_expr = FHIRConverter._generate_expr_str(
                        schema_for_key, 
                        value, 
                       self._generate_mappings_expr(value, schema_for_key, ignore_elements, level+1)
                    )
                    mappings_expr.append(self._modify_expr_str_level_based(key, level, child_mappings_expr))
                elif isinstance(value, list):
                    #if element value is of type list then recursively call this method 
                    # for each element in the list to generate expression for them as well
                    child_mappings = []
                    for valueItem in value:
                        child_mappings.append(
                            FHIRConverter._generate_expr_str(
                                schema_for_key, 
                                valueItem, 
                                self._generate_mappings_expr(valueItem, schema_for_key, ignore_elements, level+1)
                            ))
                    
                    child_mappings_expr = child_mappings[0]
                    if key in GC.FHIR_EXTENDED_ELEMENTS or len(value)>1:
                        #This is a handling for special elements like 'identifier' 
                        # which will have multiple nested structures
                        child_mappings = [f"to_json({child_mapping})" for child_mapping in child_mappings]
                        child_mappings_expr = f"array({', '.join(child_mappings)})"
                        
                    mappings_expr.append(self._modify_expr_str_level_based(key, level, child_mappings_expr))
                else:
                    mappings_expr.append(self._modify_expr_str_level_based(key, level, f"{value}.cast({schema_for_key})"))
                    
            return mappings_expr
    
    def _save_ndjson_files(self,fhir_namespace, fhir_ndjson_files_root_path,mssparkutils_client,data_split):
        """
        Saves NDJSON data chunks to the specified file path.

        Args:
            fhir_namespace (str): The FHIR namespace used for file path generation.
            fhir_ndjson_files_root_path (str): The root directory path where NDJSON files will be saved.
            mssparkutils_client: The client used for interacting with the file system (e.g., writing files).
            data_split (list): A list of NDJSON data chunks to be saved. Each chunk is a list of NDJSON strings.

        Returns:
            None
        """
 
        while data_split:
            ndjson_data = "\n".join(data_split.pop(0))
            current_timestamp = datetime.now(timezone.utc)
            ndjson_file_path = self.get_ndjson_file_path(current_timestamp, fhir_namespace)
            
            file_path = f"{fhir_ndjson_files_root_path}/{ndjson_file_path}"
            mssparkutils_client.fs_put(file_path, ndjson_data, True) 
    
    @staticmethod    
    def _split_ndjson_data(max_records_per_ndjson, resource_data_list):
        """
        Splits a list of resource data into smaller chunks, each containing
        up to a specified maximum number of records.

        Args:
            max_records_per_ndjson (int): The maximum number of records allowed per chunk.
            resource_data_list (list): The list of resource data to be split.
        
        Returns:
            list: A list of smaller chunks
        """
        data_split = [ 
            resource_data_list[i:i + max_records_per_ndjson] 
            for i in range(0, len(resource_data_list), max_records_per_ndjson)
        ]
        return data_split
           
    @staticmethod
    def remove_intermediate_updates(df: DataFrame, group_columns : list, order_by_column : str) -> DataFrame:
        """
        This method is used to remove intermediate updates from the dataframe 
        when multiple rows exists for a single row item

        Args:
            df (DataFrame): input dataframe
            group_columns (list): columns used for grouping the dataframe
            order_by_column (str): column used for ordering the dataframe

        Returns:
            DataFrame: dataframe with intermediate updates removed
        """      
        updated_df = df.groupBy(*group_columns).agg(max(order_by_column).alias(order_by_column))
        updated_df = df.join(updated_df, group_columns + [order_by_column], 'inner')
        return updated_df  
    
    @staticmethod
    def is_empty_value(value) -> bool:
        """
        This method is used to identify if a json value is empty

        Args:
            value: any valid json value

        Returns:
            bool: returns true if json value is empty otherwise false
        """        
        if (value is None or 
            (isinstance(value, str) and value.strip() == "") or
            ((isinstance(value, dict) or isinstance(value, list)) 
            and not value)):
            return True
        return False
    
    @staticmethod
    def get_mapping_for_array_element(mapping_config: list, index: int):
        """
        This method is used to fetch config mapping for a particular array element

        Args:
            mapping_config (list) : mapping config for parent array 
            index (int): index for which mapping needs to be fetched

        Returns:
            Mapping config for the child element 
        """        
        if isinstance(mapping_config, list):
            if index < len(mapping_config):
                return mapping_config[index]
            return mapping_config[0]    
        return mapping_config 
    
    @staticmethod
    def cleanup_json(json_value, mapping_config):
        """
        This method is used recursively to cleanup json which included following:
        - Removing empty values
        - Prettifying json elements present as string
        - Adding any missing brackets as per mapping config

        Args:
            json_value : any valid json value which is getting processed
            mapping_config: mapping config corresponding to the json value element 

        Returns:
            Cleaned up json value
        """        
        if FHIRConverter.is_empty_value(json_value):
            return None
        elif isinstance(json_value, dict):
            for key, value in list(json_value.items()):
                try:                            
                    if isinstance(mapping_config[key], list) and not isinstance(value, list):
                        #adding missing brackets as per mapping config
                        json_value[key]= [json_value[key]]
                    
                    if FHIRConverter.cleanup_json(json_value[key], mapping_config[key]) == None:
                        #removing empty json values
                        del json_value[key]
                except Exception as e:
                    pass
                    
            if FHIRConverter.is_empty_value(json_value):
                return None
        elif isinstance(json_value, list):
            for index, item in enumerate(json_value):
                try:
                    #prettifying json elements if present as string
                    item_json = json.loads(item)
                    json_value[index] = item_json
                except Exception as e:
                    pass
                
                if FHIRConverter.cleanup_json(json_value[index], FHIRConverter.get_mapping_for_array_element(mapping_config, index)) == None:
                    #removing empty json values
                    del json_value[index]
            if FHIRConverter.is_empty_value(json_value):
                return None

        return json_value
    
    @staticmethod
    def is_calc_column(column_config: dict) -> bool:
        """
        This method is used to check if the column config passed is for calculated column

        Args:
            column_config (dict): column config for the element

        Returns:
            bool: True if its a calculated column, False otherwise
        """        
        if 'calc' in column_config.keys():
            return True
        return False

    @staticmethod
    def _generate_expr_str(schema, value: dict, mappings:list= []) -> str:
        """
        This method is used to generate expr str for a dict mapping element 
        based on if its a calc column or a normal nested struct column

        Args:
            schema : schema for the element being processed
            value (dict): value of the dict mapping element being processed
            mappings (list, optional): child mapping expression list (if its a normal nested struct column). Defaults to [].

        Returns:
            str: generated expression string
        """      
            
        if FHIRConverter.is_calc_column(value):
            expr_str = f"{value['calc']}"
        else:
            expr_str = f"struct({', '.join(mappings)})"
        return expr_str