# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
"""
Module with class for generating flattening configuration based on AVRO schema
"""

import os
import json
from collections import namedtuple
from typing import List, Union, Dict
from pyspark.sql import SparkSession
from microsoft.fabric.hls.hds.utils.logging_helper import LoggingHelper
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants
from microsoft.fabric.hls.hds.flatten.constants import FlattenConstants as C

class FlattenConfigGenerator:
    """
    Class for generating flattening configuration based on AVRO schema
    """
    
    def __init__(self, spark: SparkSession, flatten_config_root_dir: str, avro_schema_dir: str):
        """
        Initilaize FlattenConfigGenerator instance.
        
        Args:
            spark (SparkSession): spark session to access resources/files/load dataframes
            flatten_config_root_dir (str): path to the root directory where the flattening config is located
            avro_schema_dir (str): path to directory containing avro schemas (relative to main config file path)
        """        
        self.spark: SparkSession = spark
        self._logger = LoggingHelper.get_fhirtoomop_logger(
            self.spark, self.__class__.__name__, GlobalConstants.LOGGING_LEVEL)
        
        self.flatten_config_root_dir: str = flatten_config_root_dir
        self.avro_schema_dir: str = avro_schema_dir
        
        #namedtuple for different components of flatten config file
        self.BaseReferenceNormalization = namedtuple(C.REFERENCE_NORMALIZATION, C.BASE_REFERENCE_NORMALIZATION_COMPONENTS, defaults = C.BASE_REFERENCE_NORMALIZATION_DEFAULTS)
        self.DateNormalization = namedtuple(C.DATE_NORMALIZATION, C.DATE_NORMALIZATION_COMPONENTS, defaults = C.DATE_NORMALIZATION_DEFAULTS)
        self.IdNormalization = namedtuple(C.ID_NORMALIZATION, C.ID_NORMALIZATION_COMPONENTS, defaults = C.ID_NORMALIZATION_DEFAULTS)
        self.ColumnConfig = namedtuple(C.COLUMN_CONFIG, C.COLUMN_CONFIG_COMPONENTS, defaults = C.COLUMN_CONFIG_DEFAULTS)
        self.FlatteningConfig = namedtuple(C.FLATTENING_CONFIG, C.FLATTENING_CONFIG_COMPONENTS, defaults = C.FLATTENING_CONFIG_DEFAULTS)
    
    def merge_flatten_config(self, custom_config: dict, auto_generated_config: dict) -> dict:
        """
        This method is used to merge custom config with the auto-generated config.

        Args:
            custom_config (dict): custom configuration
            auto_generated_config (dict): auto generated configuration

        Returns:
            dict: merged configuration
        """        
        for flattening_config_component in C.FLATTENING_CONFIG_COMPONENTS:
            if flattening_config_component not in custom_config.keys():
                custom_config[flattening_config_component] = auto_generated_config[flattening_config_component]
        
        # merge column configuration rules
        merged_column_rules = list(custom_config[C.COLUMN_CONFIG_SECT_COLUMNS])
        for column_rule in auto_generated_config[C.COLUMN_CONFIG_SECT_COLUMNS]:
            if (column_rule[C.COLUMN_CONFIG_ATTR_NAME] not in
                [custom_config_col[C.COLUMN_CONFIG_ATTR_NAME] for custom_config_col in custom_config[C.COLUMN_CONFIG_SECT_COLUMNS]]):
                merged_column_rules.append(column_rule)
        
        custom_config[C.COLUMN_CONFIG_SECT_COLUMNS] = merged_column_rules
        
        #merge normalization rules
        merged_normalization_rules = list(custom_config[C.COLUMN_CONFIG_SECT_NORM])
        for normalization_rule in auto_generated_config[C.COLUMN_CONFIG_SECT_NORM]:
            if (normalization_rule[C.COLUMN_CONFIG_ATTR_NAME] not in
                [custom_config_norm[C.COLUMN_CONFIG_ATTR_NAME] for custom_config_norm in custom_config[C.COLUMN_CONFIG_SECT_NORM]]):
                merged_normalization_rules.append(normalization_rule)
        
        custom_config[C.COLUMN_CONFIG_SECT_NORM] = merged_normalization_rules
        return custom_config
    
    def get_field_type(self, type_obj: dict) -> Union[Dict[str, str], None]:
        """
        This method is used to fetch the type, logical type(if exists), type name(if exists) of an element in avro schema
        
        Args:
            type_obj (dict): type object for the element (type part of an element in avro schema)

        Returns:
            Union[Dict[str, str], None]: dictionary containing type, logical type(if exists), type name(if exists) of the element
        """        
        if isinstance(type_obj, str):
            return {C.AVRO_SCHEMA_TYPE : str(type_obj)}
        elif isinstance(type_obj, dict):
            type_value_obj = {}
            if C.AVRO_SCHEMA_TYPE in type_obj.keys():
                type_value_obj[C.AVRO_SCHEMA_TYPE] = type_obj[C.AVRO_SCHEMA_TYPE]
            if C.AVRO_SCHEMA_LOGICAL_TYPE in type_obj.keys():
                type_value_obj[C.AVRO_SCHEMA_LOGICAL_TYPE] = type_obj[C.AVRO_SCHEMA_LOGICAL_TYPE]
            if C.AVRO_SCHEMA_NAME in type_obj.keys():
                type_value_obj[C.AVRO_SCHEMA_NAME] = type_obj[C.AVRO_SCHEMA_NAME]
            if C.AVRO_SCHEMA_ITEMS in type_obj.keys():
                type_value_obj[C.AVRO_SCHEMA_ITEMS] = type_obj[C.AVRO_SCHEMA_ITEMS]
            return type_value_obj
        elif isinstance(type_obj, List):
            not_null_elements = [element for element in list(type_obj) if (not isinstance(element, str)) or (C.AVRO_SCHEMA_NULL_STRING not in element)]
            return self.get_field_type(not_null_elements[0])  
    
    def get_child_fields_for_structs(self, field:dict) -> Union[List[dict], None]:
        """
        This method is used to get all the child fields for an element of type struct
        
        Args:
            field (dict): the field for which child fields are to be fetched

        Returns:
            Union[List[dict], None]: list of child fields
        """        
        while C.AVRO_SCHEMA_FIELDS not in field.keys():
            if C.AVRO_SCHEMA_TYPE in field.keys() and isinstance(field[C.AVRO_SCHEMA_TYPE], dict):
                field = field[C.AVRO_SCHEMA_TYPE]
            else:
                return None
        return field[C.AVRO_SCHEMA_FIELDS]
    
    def read_avro_schema(self, avro_schema_file: str) -> Union[dict, None] :
        """
        This method is used to read avro schema of a particular resource into a dictionary
        
        Args:
            avro_schema_file (str): name of the file containing avro schema for the resource 

        Returns:
            Union[dict, None]: avro schema content in the form of a dictionary
        """        
        avro_schema_path = os.path.join(self.avro_schema_dir, avro_schema_file)

        try:
            schema_content = self.spark.sparkContext.wholeTextFiles(
                avro_schema_path).collect()[0][1]
            return json.loads(schema_content)
        except Exception as e:
            self._logger.error(message= f"Cannot read AVRO schema located at {avro_schema_path} because of the following error: {str(e)}")
            return
            
    def generate_flatten_config(self, resource_name: str, avro_schema_file: str) ->Union[str, None]:
        """
        This method is used to generate the flattening config with default normalization rules for a particular resource
        
        Args:
            resource_name (str): name of the resource for which flattening config is to be generated
            avro_schema_file (str): name of the file containing avro schema for the resource

        Returns:
            Union[str, None]: flattening config in the form of a json string
        """        
        avro_schema_content = self.read_avro_schema(avro_schema_file)
        if avro_schema_content is None:
            return
        all_fields = avro_schema_content[C.AVRO_SCHEMA_FIELDS]
        
        columns = [self.ColumnConfig(name=C.META_LAST_UPDATED_FIELD_NAME, expression=C.META_LAST_UPDATED_FIELD_EXP)._asdict()]
        
        normalization_rules = [self.DateNormalization(C.META_LAST_UPDATED_FIELD_NAME)._asdict()]
        normalization_rules.append(self.IdNormalization(resourceType=f"'{resource_name}'")._asdict())
        normalization_rules += self.generate_default_normalization_rules(all_fields)
        config = self.FlatteningConfig(name= f'{resource_name} auto configuration', normalization=normalization_rules, columns=columns)._asdict()
        return json.dumps(config)
    
    def generate_ref_norm_rules_for_special_fhir_types(self, field_name:str, field_type: dict) -> List[dict]:
        """
        This method is used to generate reference normalization rules for special fhir 
        types like Signatue.who, Annotation.authorReference, Identifier.assigner
        
        Args:
            field_name (str): name of the field
            field_type (dict): type of the field

        Returns:
            List[dict]: list of normalization rules
        """        
        normalization_rules = []
        ref_norm_rule = self.BaseReferenceNormalization(name=field_name)._asdict()

        if self.check_complex_field_type(field_type, C.FHIR_TYPE_SIGNATURE):
            ref_norm_rule[C.REFERENCE_NORM_NESTED_REF] = C.FHIR_TYPE_SIGNATURE_WHO
            normalization_rules.append(ref_norm_rule)
            ref_norm_rule[C.REFERENCE_NORM_NESTED_REF] = C.FHIR_TYPE_SIGNATURE_ON_BEHALF_OF
            normalization_rules.append(ref_norm_rule)
        elif self.check_complex_field_type(field_type, C.FHIR_TYPE_ANNOTATION):
            ref_norm_rule[C.REFERENCE_NORM_NESTED_REF] = C.FHIR_TYPE_ANNOTATION_AUTHOR_REF
            normalization_rules.append(ref_norm_rule)
        elif self.check_complex_field_type(field_type, C.FHIR_TYPE_IDENTIFIER):
            ref_norm_rule[C.REFERENCE_NORM_NESTED_REF] = C.FHIR_TYPE_IDENTIFIER_ASSIGNER
            normalization_rules.append(ref_norm_rule)
        elif self.check_complex_field_type(field_type, C.FHIR_TYPE_CODEABLE_REFERENCE):
            ref_norm_rule[C.REFERENCE_NORM_NESTED_REF] = C.FHIR_TYPE_COD_REF_REFERENCE
            normalization_rules.append(ref_norm_rule)
        return normalization_rules
    
    def generate_date_norm_rules_for_special_fhir_types(self, field_name:str, field_type: dict) -> List[dict]:
        """
        This method is used to generate date normalization rules for special fhir 
        types like Period, Attachment.creation, Signature.when, Annotation.time
        
        Args:
            field_name (str): name of the field
            field_type (dict): type of the field

        Returns:
            List[dict]: list of normalization rules
        """        
        normalization_rules = []

        if self.check_complex_field_type(field_type, C.FHIR_TYPE_PERIOD):
            normalization_rules += [self.DateNormalization(f'{field_name}.{C.FHIR_TYPE_PERIOD_START}')._asdict(), 
                                    self.DateNormalization(f'{field_name}.{C.FHIR_TYPE_PERIOD_END}')._asdict()]
        elif self.check_complex_field_type(field_type, C.FHIR_TYPE_ATTACHMENT):
            normalization_rules.append(self.DateNormalization(f'{field_name}.{C.FHIR_TYPE_ATTACHMENT_CREATION}')._asdict())
        elif self.check_complex_field_type(field_type, C.FHIR_TYPE_SIGNATURE):
            normalization_rules.append(self.DateNormalization(f'{field_name}.{C.FHIR_TYPE_SIGNATURE_WHEN}')._asdict())         
        elif self.check_complex_field_type(field_type, C.FHIR_TYPE_ANNOTATION):
            normalization_rules.append(self.DateNormalization(f'{field_name}.{C.FHIR_TYPE_ANNOTATION_TYPE}')._asdict())
        return normalization_rules
    
    def check_complex_field_type(self, field_type: dict, expected_field_type: str) -> bool:
        """
        Verifies the field type against the expected field type. 
        Returns true if the field type matches with the expected field type else returns false.
        
        Args:
            field_type (dict): actual field type object
            expected_field_type (str): expected field type

        Returns:
            bool: whether the field type matches with the expected type.
        """    
        
        #This is to prevent the match to a datatype ending with the same name 
        #we are looking for but actually is not.   
        expected_field_type_with_dot = f".{expected_field_type}"
        
        if isinstance(field_type, str) and expected_field_type_with_dot in field_type:
            return True
        if isinstance(field_type, dict) and expected_field_type_with_dot in field_type[C.AVRO_SCHEMA_TYPE]:
            return True 
        if (isinstance(field_type, dict) and field_type[C.AVRO_SCHEMA_TYPE] == C.AVRO_SCHEMA_RECORD and 
            C.AVRO_SCHEMA_NAME in field_type.keys() and field_type[C.AVRO_SCHEMA_NAME] == expected_field_type):
            return True
        if (isinstance(field_type, dict) and field_type[C.AVRO_SCHEMA_TYPE] == C.AVRO_SCHEMA_ARRAY and 
            C.AVRO_SCHEMA_ITEMS in field_type.keys() and expected_field_type_with_dot in field_type[C.AVRO_SCHEMA_ITEMS] ):
            return True
        return False

    def is_field_type_date(self, field_type:dict) -> bool:
        """
        This method is used to check if the field type is date. 
        Returns True if it is date type else returns false
        
        Args:
            field_type (dict): avro field type object

        Returns:
            bool: whether the field is of type date or not
        """        
        if (field_type[C.AVRO_SCHEMA_TYPE] in C.AVRO_SCHEMA_DATE_TYPES and 
            C.AVRO_SCHEMA_LOGICAL_TYPE in field_type.keys() and 
            field_type[C.AVRO_SCHEMA_LOGICAL_TYPE] in C.AVRO_SCHEMA_DATE_LOGICAL_TYPES):
            return True
        return False
    
    def is_field_primitive_type(self, field_type:dict) -> bool:
        """
        This method is used to check if the field is of primitve datatype 
        i.e. if field is of type string, bool, int or decimal

        Args:
            field_type (dict): avro field type object

        Returns:
            bool: whether the field is of primitive type
        """        
        if (field_type[C.AVRO_SCHEMA_TYPE] == C.FHIR_STRING_TYPE or 
            (field_type[C.AVRO_SCHEMA_TYPE] == C.FHIR_INT_TYPE and 
             C.AVRO_SCHEMA_LOGICAL_TYPE not in field_type.keys()) or 
            field_type[C.AVRO_SCHEMA_TYPE] == C.FHIR_BOOL_TYPE or
            (C.AVRO_SCHEMA_LOGICAL_TYPE in field_type.keys() and 
             field_type[C.AVRO_SCHEMA_LOGICAL_TYPE] == C.FHIR_DECIMAL_TYPE)):
            return True
        return False
    
    def generate_default_normalization_rules(self, fields: List[dict], nesting_level: int = 1, field_name_prefix: str = "", is_parent_array: bool = False) -> List[dict]:
        """
        This method is used to generate default normalization rules.
        
        Args:
            fields (List[dict]): list of fields for processing 
            nesting_level (int, optional): Current nesting level. Defaults to 1.
            field_name_prefix (str, optional): any prefix for the field name(this may contain the parent field name). Defaults to "".
            is_parent_array (str, optional): if the parent element is an array

        Returns:
            List[dict]: list of normalization rules
        """        
        ref_norm_rules = []
        date_norm_rules = []
        child_normalization_rules = []
        
        for field in fields:
            if (field is None) or (not isinstance(field, dict)) or (C.AVRO_SCHEMA_TYPE not in field.keys()):
                continue
            field_type = self.get_field_type(field[C.AVRO_SCHEMA_TYPE])
            if field_type is None or (not isinstance(field_type, dict)) or C.AVRO_SCHEMA_TYPE not in field_type.keys():
                continue
            
            if self.is_field_primitive_type(field_type):
                continue
            
            is_single_reference_element = self.check_complex_field_type(field_type, C.FHIR_TYPE_REFERENCE)
            is_reference_array = field_type[C.AVRO_SCHEMA_TYPE] == C.AVRO_SCHEMA_ARRAY and self.check_complex_field_type(field_type[C.AVRO_SCHEMA_ITEMS], C.FHIR_TYPE_REFERENCE)
            
            if (is_single_reference_element or is_reference_array) and nesting_level <= C.NORMALIZATION_MAX_NESTING_LEVEL: 
                if field_name_prefix == "":
                    ref_norm_rule = self.BaseReferenceNormalization(name=field[C.AVRO_SCHEMA_NAME])._asdict()     
                else:
                    ref_norm_rule = self.BaseReferenceNormalization(name=field_name_prefix.replace(".", ""))._asdict()
                    ref_norm_rule[C.REFERENCE_NORM_NESTED_REF] = field[C.AVRO_SCHEMA_NAME]
                if is_reference_array:
                    ref_norm_rule[C.REFERENCE_NORM_NESTED_ARRAY] = True
                ref_norm_rules.append(ref_norm_rule)
            elif is_parent_array == False and self.is_field_type_date(field_type) and nesting_level <= C.NORMALIZATION_MAX_NESTING_LEVEL:
                date_norm_rules.append(self.DateNormalization(field_name_prefix + field[C.AVRO_SCHEMA_NAME])._asdict())
            elif field_type[C.AVRO_SCHEMA_TYPE] == C.AVRO_SCHEMA_RECORD and nesting_level <= C.NORMALIZATION_MAX_NESTING_LEVEL:
                child_fields = self.get_child_fields_for_structs(field)
                if child_fields is not None:
                    child_normalization_rules += self.generate_default_normalization_rules(child_fields, nesting_level+1, f'{field_name_prefix}{field[C.AVRO_SCHEMA_NAME]}.')
            elif field_type[C.AVRO_SCHEMA_TYPE] == C.AVRO_SCHEMA_ARRAY and isinstance(field_type[C.AVRO_SCHEMA_ITEMS], dict) and nesting_level <= C.NORMALIZATION_MAX_NESTING_LEVEL:
                child_fields = self.get_child_fields_for_structs(field_type[C.AVRO_SCHEMA_ITEMS])
                if child_fields is not None:
                    child_normalization_rules += self.generate_default_normalization_rules(child_fields, nesting_level+1, f'{field_name_prefix}{field[C.AVRO_SCHEMA_NAME]}.', True)
            elif nesting_level < C.NORMALIZATION_MAX_NESTING_LEVEL:
                child_normalization_rules += self.generate_ref_norm_rules_for_special_fhir_types(field[C.AVRO_SCHEMA_NAME], field_type)
                if is_parent_array == False and field_type[C.AVRO_SCHEMA_TYPE] != C.AVRO_SCHEMA_ARRAY:
                    child_normalization_rules += self.generate_date_norm_rules_for_special_fhir_types(field[C.AVRO_SCHEMA_NAME], field_type)
            
        return (ref_norm_rules + date_norm_rules + child_normalization_rules)