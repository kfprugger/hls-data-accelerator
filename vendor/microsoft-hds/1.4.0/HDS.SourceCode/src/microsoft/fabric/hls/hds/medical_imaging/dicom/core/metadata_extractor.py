# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
"""
Module with a class to extract metadata tags from dicom file
"""

import json
from pydicom import dcmread
import os
from datetime import datetime
from pyspark.sql.functions import udf
from pyspark.sql.types import *
from microsoft.fabric.hls.hds.medical_imaging.dicom.core.constants import ImagingStudyConstants as C
from collections.abc import Callable
from typing import Any
from pydicom.dataelem import DataElement
from pydicom.dataset import FileDataset

@udf(MapType(StringType(), StringType()))
def extract_metadata(dcm_file_path: str, source_path: str, mount_path: str, stop_before_pixels: bool, suppress_validation_tags: bool):
    """
    This method is used to extract metadata tags from dcm file content

    Args:
        dcm_file_path (str): path of the dcm file
        source_path (str): path of the source folder
        mount_path (str): path where the source folder is mounted

    Returns:
        dict: a dictionary containing information about all the tags into json structure, 
        and all the individual tags which needs to be extracted as columns
    """        
        
    try:
        leaf_path = os.path.relpath(dcm_file_path, source_path)        
        dcm_mount_full_path = os.path.join(mount_path, leaf_path)
                
        if not stop_before_pixels:           
            ds = dcmread(dcm_mount_full_path)
            if 'PixelData' in ds:
                # If the dataset has pixel data, remove it to save memory
                del ds.PixelData
        else:
            ds = dcmread(dcm_mount_full_path,stop_before_pixels=True)
           
        # transform_to_json_dict() method is used get all the tags information in the form 
        # of a json dictionary object as per Dicom json model
        tags_json = MetadataExtractorUtils.transform_to_json_dict(ds,suppress_invalid_tags=suppress_validation_tags)
        

        metadata = {}
        
        # the below part of the code is used to extract dicom tags individually 
        # as per the constant defined
        failed_tags_extract = []
        for tag_key in C.DEFAULT_TAGS_AS_COLUMN:
            try:
                tag_value = str(ds[tag_key].value)                
                metadata[tag_key.lower()] = tag_value
            except Exception as e:
                failed_tags_extract.append(tag_key)
                metadata[tag_key.lower()] = ""
        
        if failed_tags_extract:
            metadata[C.FAILED_TAGS_ATTR_NAME] = failed_tags_extract
        metadata[C.TAGS_JSON_COLUMN_NAME] = json.dumps(tags_json)
        return metadata
    except Exception as ex:
        return { C.ERROR_ATTR_NAME : str(ex) }

class MetadataExtractorUtils:
        
    @staticmethod
    def transform_to_json_dict(
        dataset: FileDataset,
        bulk_data_threshold: int = 1024,
        bulk_data_element_handler: Callable[[DataElement], str] = None,
        suppress_invalid_tags: bool = False,
    ) -> dict[str, Any]:
        """
        Return a dictionary representation of the :class:`Dataset`

        Args:
        bulk_data_threshold : int, optional
            Threshold for the length of a base64-encoded binary data element
            above which the element should be considered bulk data and the
            value provided as a URI rather than included inline (default:
            ``1024``). Ignored if no bulk data handler is given.
        bulk_data_element_handler : callable, optional
            Callable function that accepts a bulk data element and returns a
            JSON representation of the data element (dictionary including the
            "vr" key and either the "InlineBinary" or the "BulkDataURI" key).
        suppress_invalid_tags : bool, optional
            Flag to specify if errors while serializing tags should be logged
            and the tag dropped or if the error should be bubbled up.

        Returns:
        dict
            :class:`Dataset` representation based on the DICOM JSON Model.
        """

        json_dataset = {}
        for key in dataset.keys():
            json_key = f"{key:08X}"
            try:
                data_element = dataset[key]
                json_dataset[json_key] = data_element.to_json_dict(
                    bulk_data_element_handler=bulk_data_element_handler,
                    bulk_data_threshold=bulk_data_threshold,
                )
            except Exception as exc:
                if not suppress_invalid_tags:
                    raise exc

                # Handle invalid tags by adding them to the dictionary
                try:
                    data_element = dataset[key]
                    json_dataset[json_key] = {'vr' : data_element.VR, 'Value': [f'{data_element.value}']}

                except Exception as inner_exc:
                    raise inner_exc

        return json_dataset