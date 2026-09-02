# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
"""
Module with class for doing flattening functionality based on provided or internal configuration
"""
import json
import os
from typing import Dict, Union, List, cast

from pyspark.sql import SparkSession
from pyspark.sql import DataFrame, functions as F, types as T, Column
from microsoft.fabric.hls.hds.flatten.normalization.normalization_manager import FlattenNormalization
from microsoft.fabric.hls.hds.flatten.constants import FlattenConstants as C
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.utils.dataframe_utils import encode_df_string, \
    flatten_struct, flatten_all_dataframe_struct, stringify_complex_types
from microsoft.fabric.hls.hds.flatten.flatten_config_generator import FlattenConfigGenerator as FCG
from microsoft.fabric.hls.hds.utils.logging_helper import LoggingHelper
from microsoft.fabric.hls.hds.utils.utils import Utils

class FlattenCore:
    """
    Class for doing flatten functionality based on provided or internal configuration
    """

    def __init__(self, spark: SparkSession, source_schema_root_dir: str, transformation_config_root_dir: str):
        """
        Initialize FlattenCore instance

        Arguments:
        - spark - spark session to access resources/files/load dataframes
        - source_schema_root_dir - str - path to where the source schema is located
        - transformation_config_root_dir: str - the root directory of where the transformation config is located.
        """
        self.source_schema_root_dir = source_schema_root_dir
        self.transformation_config_root_dir = transformation_config_root_dir
        def __check_udf_registered(udf_name: str) -> bool:
            """
            Check if UDF is registered in spark session
            """
            return udf_name in [func.name for func in self.spark.catalog.listFunctions()]

        self.spark: SparkSession = spark
        self._logger = LoggingHelper.get_silveringestion_logger(
            self.spark, self.__class__.__name__, GC.LOGGING_LEVEL)
        # support normalization
        if not __check_udf_registered(C.NORM_UDF_NORM_DATE):
            self.spark.udf.register(
                C.NORM_UDF_NORM_DATE, FlattenNormalization.normalize_date, T.TimestampType())
        if not __check_udf_registered(C.NORM_UDF_NORM_RESOURCE_ID):
            self.spark.udf.register(
                C.NORM_UDF_NORM_RESOURCE_ID, FlattenNormalization.normalize_resource_id, T.StringType())
        if not __check_udf_registered(C.NORM_UDF_NORM_REFERENCE_STRUCT):
            self.spark.udf.register(
                C.NORM_UDF_NORM_REFERENCE_STRUCT, FlattenNormalization.normalize_ref_struct, C.NORM_REF_STRUCT_UDF_SCHEMA)
        if not __check_udf_registered(C.NORM_UDF_NORM_REFERENCE_ARRAY):
            self.spark.udf.register(
                C.NORM_UDF_NORM_REFERENCE_ARRAY, FlattenNormalization.normalize_ref_array, C.NORM_REF_ARRAY_UDF_SCHEMA)

        self.flatten_config_generator = FCG(self.spark, self.transformation_config_root_dir, self.source_schema_root_dir)

    @staticmethod
    def __iter_func(column_settings: Dict[str, str]) -> Column:
        """
        Iterates through column configuration for current resource/dataframe

        It supports expression evaluation or just column evaluation
        """
        if column_settings[C.COLUMN_CONFIG_ATTR_STYLE] == \
                C.COLUMN_FUNCTION_EXPRESSION:
            return F.expr(column_settings[C.COLUMN_CONFIG_ATTR_EXPRESSION]).alias(
                column_settings[C.COLUMN_CONFIG_ATTR_NAME])
        elif column_settings[C.COLUMN_CONFIG_ATTR_STYLE] == \
                C.COLUMN_FUNCTION_COLUMN:
            return F.col(column_settings[C.COLUMN_CONFIG_ATTR_EXPRESSION]).alias(
                column_settings[C.COLUMN_CONFIG_ATTR_NAME])
        # default case - just return column name
        else:
            return F.col(column_settings[C.COLUMN_CONFIG_ATTR_EXPRESSION]).alias(
                column_settings[C.COLUMN_CONFIG_ATTR_NAME])

    def __process_flattening(self,
                             source_df: DataFrame,
                             columns_config: Dict,
                             explode_config: Union[Dict[str,
                                                        str], None] = None,
                             append: bool = False,
                             auto_flatten_struct: bool = False) -> DataFrame:
        """
        Process Flattening of Resource Type or Child Resource Type with
        rules from column configuration file

        Arguments:
        - source_df: DataFrame - Parent Dataframe with loaded parent dataframe
        - columnsConfig: list - columns configuration  - list of columns with their names,
            expression to calculate based on source_df, or column function just to extract
        - explodeConfig: list - optional parameter with explodeConfig section.
            Used to specify explode expression and alias name for
            exploded entries (used for child resources)
        - append: bool - specify either append columns from configuration. If no,
            column from source dataframe will be omitted
        - auto_flatten_struct: bool - specify either flatten struct columns
        """
        index_column = None
        result_df = source_df
        if explode_config is not None and len(explode_config) > 0:
            # if explode config is present - do the explode operation first

            # reading index column name for indexing exploded list items
            index_column = C.INDEX_COLUMN_DEFAULT
            
            if C.EXPLODE_SECT_ATTR_INDEX in explode_config:
                index_column = explode_config[C.EXPLODE_SECT_ATTR_INDEX]
            # encode if index column contains .(dot)
            result_df = \
                result_df.\
                select([F.col('*')] +
                       [F.posexplode(F.expr(
                           explode_config[C.EXPLODE_SECT_ATTR_EXPRESSION])).
                        alias(index_column, explode_config[C.EXPLODE_SECT_ATTR_NAME])]).\
                withColumn(index_column, F.col(
                    encode_df_string(index_column))+1)

        # if append mode and auto_flatten_struct is True - flatten all struct columns
        # if append mode is False - we will iterate through column configuration only
        if append and auto_flatten_struct:
            result_df = flatten_all_dataframe_struct(result_df)

        if columns_config is not None:
            initial_columns: List[Column] = []
            if index_column:
                initial_columns += [F.col(encode_df_string(index_column))]
            if append:
                initial_columns = [F.col('*')]
            # iterate through column configuration and select columns based on that configuration
            # if we are in append mode - we skip columns with the same name as in source dataframe
            # Example:
            # column configuration defines 'id' column with some rule
            # and the same time 'id' is column in dataframe
            # in that case we skip 'id' column from column_ configuration
            # and use only from source dataframe
            result_df = result_df.select(
                initial_columns +
                [FlattenCore.__iter_func(set) for set in columns_config if not append or
                 set[C.COLUMN_CONFIG_ATTR_NAME] not in result_df.columns])

            # process columns which has optional attribute 'flatten'
            # if flatten type struct - do struct flattening for that column
            for flat_struct in columns_config:
                if C.COLUMN_CONFIG_ATTR_FLATTEN in flat_struct\
                    and flat_struct[C.COLUMN_CONFIG_ATTR_FLATTEN] == \
                        C.COLUMN_FLATTEN_TYPE_STRUCT:
                    result_df =\
                        flatten_struct(
                            result_df,
                            flat_struct[C.COLUMN_CONFIG_ATTR_NAME],
                            flat_struct[C.COLUMN_CONFIG_ATTR_NAME] + '_')

            return result_df
        # if no columns configuration - just return source dataframe
        
        return source_df

    def __process_normalization(self,
                                source_df: DataFrame,
                                settings: Dict) -> DataFrame:
        """
        Process Normalization of columns in dataframe
        based on provided configuration

        Arguments:
        - source_df: DataFrame - Dataframe with loaded data
        - settings: list - parameter with normalization section.
            We process normalization section after flattening and add/replace columns
            with their normalized representation
        """
        result_df = source_df

        # process normalization procedure
        if settings:
            for norm_config_item in settings:
                norm_name = norm_config_item[C.NORM_CONF_NAME]
                
                norm_expression = None
                if C.NORM_CONF_EXPRESSION in norm_config_item:
                    norm_expression = norm_config_item[C.NORM_CONF_EXPRESSION]
                norm_type = norm_config_item[C.NORM_CONF_TYPE]
                # by default - copy original column with prefix is true
                norm_copy_original_column = True

                # Date field normalization
                if norm_type == C.NORM_CONF_TYPE_DATE and norm_expression is None:
                    if "." in norm_name:
                        norm_elements = norm_name.split(".")
                        result_df = result_df.withColumn(norm_elements[0], 
                                                         F.col(norm_elements[0]).\
                                                             withField(norm_elements[1] + C.NORM_COPY_POSTFIX, F.col(norm_name)).\
                                                                withField(norm_elements[1], F.expr(f"{C.NORM_UDF_NORM_DATE}({norm_name})")))
                    else:
                        norm_expression = f"{C.NORM_UDF_NORM_DATE}(`{norm_name}`)"
                # add transform for different links types
                
                # Resource id normalization
                if norm_type == C.NORM_CONF_TYPE_RESOURCE and norm_expression is None:
                    # we don't need to copy original column if output name
                    # is different compared to input id column
                    if norm_name != norm_config_item[C.NORM_CONF_REFERENCE_ID]:
                        norm_copy_original_column = False
                    
                    source_system = None
                    if C.NORM_CONF_SOURCE_SYSTEM in norm_config_item:
                        source_system = norm_config_item[C.NORM_CONF_SOURCE_SYSTEM]
                        
                        # resource.id normalization expression
                        norm_expression = f"{C.NORM_UDF_NORM_RESOURCE_ID}({norm_config_item[C.NORM_CONF_REFERENCE_ID]}, {norm_config_item[C.NORM_CONF_REFERENCE_TYPE]}, {source_system})"
                        
                        try:
                            result_df = FlattenNormalization.normalize_resource_identifier(
                                df=result_df, 
                                identifier_column=GC.DEFAULT_SILVER_FHIR_IDENTIFIER_COL,
                                id_column=norm_config_item[C.NORM_CONF_REFERENCE_ID], 
                                source_system_column=source_system
                            )
                        except ValueError as value_error:
                            error_message = LC.RESOURCE_IDENTIFIER_NORMALIZATION_ERR_MSG.format(resource=norm_config_item[C.NORM_CONF_REFERENCE_TYPE],
                                                                                                identifier_column=GC.DEFAULT_SILVER_FHIR_IDENTIFIER_COL,
                                                                                                error_message=str(value_error))
                            self._logger.error(error_message)
                    
                    
                # Reference normalization
                if norm_type == C.NORM_CONF_REFERENCE:
                    # The default nestedArray normalization configuration value is False
                    norm_copy_original_column = False
                    norm_nested_array = C.NORM_CONF_ATTR_NESTED_ARRAY_DEFAULT
                    if C.NORM_CONF_NESTED_ARRAY in norm_config_item and isinstance(norm_config_item[C.NORM_CONF_NESTED_ARRAY], bool):
                        norm_nested_array = norm_config_item[C.NORM_CONF_NESTED_ARRAY]
                    
                    # Normalize nested reference objects on level 2 (both struct and array reference objects)
                    if C.NORM_CONF_NESTED_REFERENCE in norm_config_item:
                        norm_expression = None
                        original_col_schema = result_df.schema[norm_name].dataType
                        nested_ref_name = norm_config_item[C.NORM_CONF_NESTED_REFERENCE]
                        
                        try:
                            if original_col_schema:
                                normalize_nested_ref_udf = FlattenNormalization.create_normalize_nested_ref_udf(original_col_schema, nested_ref_name, norm_nested_array)
                                result_df = result_df.withColumn(norm_name, normalize_nested_ref_udf(result_df[norm_name], result_df[GC.DEFAULT_SILVER_FHIR_TABLE_MSFT_SOURCE_SYSTEM_COL]))
                            else:
                                self._logger.info(LC.REFERENCE_NORMALIZATION_INFO_MSG.format(column=norm_name,nested_ref_name=nested_ref_name, schema=type(original_col_schema)))
                        except ValueError as value_error:
                            error_message = LC.REFERENCE_NORMALIZATION_ERR_MSG.format(column=norm_name) + str(value_error)
                            self._logger.error(error_message)
                            raise ValueError(error_message) from value_error

                    elif norm_nested_array:
                        # Normalize reference array objects on level 1
                        norm_expression = f"{C.NORM_UDF_NORM_REFERENCE_ARRAY}({norm_name}, {GC.DEFAULT_SILVER_FHIR_TABLE_MSFT_SOURCE_SYSTEM_COL})"
                    else:
                        # Normalize reference struct objects on level 1
                        norm_expression = f"{C.NORM_UDF_NORM_REFERENCE_STRUCT}({norm_name}, {GC.DEFAULT_SILVER_FHIR_TABLE_MSFT_SOURCE_SYSTEM_COL})"

                # if file has actual value for copy_original_column - read it
                if C.NORM_CONF_PRESERVE_OLD_VALUE in norm_config_item:
                    norm_copy_original_column = norm_config_item[C.NORM_CONF_PRESERVE_OLD_VALUE]

                if norm_expression:
                    if norm_copy_original_column and norm_name in result_df.columns:
                        result_df = result_df.withColumn(
                            norm_name+C.NORM_COPY_POSTFIX,
                            col=F.col(encode_df_string(norm_name)))
                    result_df = result_df.withColumn(
                        colName=norm_name,
                        col=F.expr(norm_expression)
                    )
            return result_df
        # if no normalization configuration - just return source dataframe
        return source_df

    def process_dataframe(self, resource_config: Dict, input_df: DataFrame) -> Dict[str, DataFrame]:
        """
        Process Dataframe for specified ResourceType

        Arguments:
        - resource_config: The transformation configuration for this dataframe
        - input_df: DataFrame - Input data frame 
       
        - Returns:
            - A dictionary where the key is the table name and the value is a DataFrame pertaining to the table
        """
        response = {}
        if resource_config is not None:
            resource_type = resource_config[GC.SILVER_CONFIG_NAME_KEY]
            avro_schema_file = resource_config[C.MAIN_CONFIG_SECT_SCHEMA][C.SCHEMA_CONFIG_ATTR_PATH]
            
            extend_with_default_rules = C.DEFAULT_EXTEND_WITH_DEFAULT_RULES
            config_path = None
            columns_schema = None
            
            if C.MAIN_CONFIG_ATTR_COLUMN_SCHEMA in resource_config.keys():
                config_path = f'{self.transformation_config_root_dir}/{resource_config[C.MAIN_CONFIG_ATTR_COLUMN_SCHEMA]}'
            
            # Replaced the logic to validate the config path exists
            # We instead just tried to read the config file and if a FileNotFoundError is thrown, 
            # we generate the column configuration from the provided resource schema 
            # TODO: Update to use msspark file utils to validate if config path exists. https://dev.azure.com/dynamicscrm/Solutions/_workitems/edit/3571514
            try:
                if config_path is not None:
                    columns_schema_content = Utils.load_config_file(self.spark, config_path)
                    columns_schema = json.loads(columns_schema_content)
                    self._logger.info(LC.FLATTENING_LOADING_CONFIGURATION_AT_PATH.format(config_path=config_path, resource_type=resource_type))
                    
                    if C.EXTEND_WITH_DEFAULT_RULES_PROPERTY in columns_schema.keys():
                        extend_with_default_rules = columns_schema[C.EXTEND_WITH_DEFAULT_RULES_PROPERTY]

                    if extend_with_default_rules:
                        columns_schema = self.flatten_config_generator.merge_flatten_config(
                            columns_schema,
                            json.loads(self.flatten_config_generator.generate_flatten_config(resource_type, avro_schema_file)))
                
                else:
                    self._logger.info(LC.FLATTENING_GENERATING_CONFIGURATION.format(resource_type=resource_type))
                    columns_schema = json.loads(self.flatten_config_generator.generate_flatten_config(resource_type, avro_schema_file))
            except FileNotFoundError as ex:
                    self._logger.debug(LC.FLATTENING_INVALID_COLUMN_CONFIGURATION.format(resource_type=resource_type, config_path=config_path, ex_message=str(ex)))
                    # Use the provided schema to generate the column configuration when the config is missing
                    columns_schema = json.loads(self.flatten_config_generator.generate_flatten_config(resource_type, avro_schema_file))
                    
            response[resource_type] = self.__process_resource(
                columns_schema=columns_schema,
                input_df=input_df)

            if C.MAIN_CONFIG_SECT_CHILDREN in resource_config:
                for child in resource_config[C.MAIN_CONFIG_SECT_CHILDREN]:
                    child_columns_config = \
                            child[C.MAIN_CONFIG_ATTR_COLUMN_SCHEMA]
                    child_columns_schema_content = Utils.load_config_file(self.spark, f'{self.transformation_config_root_dir}/{child_columns_config}')
                    child_col_schema = json.loads(
                        child_columns_schema_content)
                    # process child resource configuration on parent data frame
                    response[child[C.MAIN_CONFIG_ATTR_NAME]] = \
                            self.__process_resource(
                        columns_schema=child_col_schema,
                        input_df=input_df)
        return response

    def __process_resource(self, columns_schema: Dict[str, Union[str, bool, Dict[str, str]]],
                           input_df: DataFrame) -> DataFrame:
        """
        Processing resource with specified config
        Arguments:
        - columns_schema: dict - column schema configuration for the resource
        - input_df: DataFrame - Input data frame for resource which will be processed
        """
        if columns_schema is None:
            # if no configuration - just return source dataframe
            return input_df
        
        append_columns = C.MAIN_CONFIG_ATTR_APPEND_DEFAULT
        if C.MAIN_CONFIG_ATTR_APPEND in columns_schema:
            if isinstance(columns_schema[C.MAIN_CONFIG_ATTR_APPEND], bool):
                append_columns = columns_schema[C.MAIN_CONFIG_ATTR_APPEND]

        stringify_complex_columns = C.MAIN_CONFIG_ATTR_STRINGIFY_DEFAULT       
        if C.MAIN_CONFIG_ATTR_STRINGIFY in columns_schema:
            if isinstance(columns_schema[C.MAIN_CONFIG_ATTR_STRINGIFY], bool):
                stringify_complex_columns = columns_schema[C.MAIN_CONFIG_ATTR_STRINGIFY]

        auto_flatten_columns = C.MAIN_CONFIG_ATTR_AUTO_FLATTEN_DEFAULT
        if C.MAIN_CONFIG_ATTR_AUTO_FLATTEN in columns_schema:
            if isinstance(columns_schema[C.MAIN_CONFIG_ATTR_AUTO_FLATTEN], bool):
                auto_flatten_columns = columns_schema[C.MAIN_CONFIG_ATTR_AUTO_FLATTEN]

        explode_config: Dict[str, str] = {}
        if C.COLUMN_CONFIG_SECT_EXPLODE in columns_schema:
            explode_config = \
                cast(Dict[str, str],
                        columns_schema[C.COLUMN_CONFIG_SECT_EXPLODE])
        normalization_config = None
        if C.COLUMN_CONFIG_SECT_NORM in columns_schema:
            normalization_config = columns_schema[C.COLUMN_CONFIG_SECT_NORM]

        # process resource type flattening
        temp_df = self.__process_flattening(
            source_df=input_df,
            columns_config=cast(
                Dict, columns_schema[C.COLUMN_CONFIG_SECT_COLUMNS]),
            explode_config=explode_config,
            append=bool(append_columns),
            auto_flatten_struct=bool(auto_flatten_columns))
        
        # process resource type normalization
        if normalization_config:
            temp_df = self.__process_normalization(
                source_df=temp_df,
                settings=cast(Dict, normalization_config)
            )
        
        # stringify complex type fields in the dataframe
        if stringify_complex_columns:
            temp_df = stringify_complex_types(temp_df)
        
        return temp_df