# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
"""
Module with a class containing static methods used for dicom metadata to fhir ndjson conversion
"""
from pyspark.sql import DataFrame
import pydicom
import re
import json
import os
from datetime import datetime
from microsoft.fabric.hls.hds.medical_imaging.dicom.core.constants import ImagingStudyConstants as C
from microsoft.fabric.hls.hds.utils.fhir_converter_helper import FHIRConverter 
from pyspark.sql.types import *
from pyspark.sql.functions import *
import uuid

class DicomToFhirUtils:
    """
    Class containing static methods used for dicom metadata to ImagingStudy fhir ndjson conversion
    """      
    
    @staticmethod
    def get_tag_for_keyword(keyword: str) -> str:
        """
        This method is used to get the tag id for a tag keyword 
        using the pydicom OOB data dict

        Args:
            keyword (str): tag keyword

        Returns:
            str: a string representation of tag id
        """        
        dicom_tag = pydicom.datadict.tag_for_keyword(keyword)
        return f"{dicom_tag >> 16:04X}{dicom_tag & 0xFFFF:04X}"
    
    @staticmethod
    def pre_process_dataframe(incremental_df: DataFrame, full_df: DataFrame) -> DataFrame:
        """
        Pre-processes the given DataFrame by joining it with an existing DataFrame based on study IDs.

        This method is used to pre-process the dataframe before the fhir conversion
        - Get all the instances of ImagingStudy rows from full dataframe which are not present in incremental dataframe
        - Join the incremental dataframe with full dataframe to get the final dataframe for fhir conversion
        Args:
            incremental_df (DataFrame): dataframe with incremental data
            full_df (DataFrame): dataframe with already ingested ImagingStudy rows + incremental data
            
        Returns:
            DataFrame: A DataFrame resulting from the join operation between the full DataFrame and the incremental study IDs.
        """
        #get a dataframe with existing ImagingStudy rows as well from bronze metastore table
        #full_df = full_df.drop(C.TAGS_JSON_COLUMN_NAME, C.TAGS_METADATA_STRING)
        full_df = full_df.withColumnRenamed(C.SILVER_SOURCE_SYSTEM_COLUMN_NAME, C.SOURCE_SYSTEM_COLUMN_NAME)        
        incremental_study_ids = incremental_df.select(C.GROUP_BY_ELEMENTS[C.FHIR_IMAGING_STUDY_RES_NAME]).distinct()
        df = full_df.join(incremental_study_ids, C.GROUP_BY_ELEMENTS[C.FHIR_IMAGING_STUDY_RES_NAME], 'inner')
        return df