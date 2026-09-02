import json
from pyspark.sql import SparkSession, types as T
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants

class ExtensionParser:
    """
    Class for retrieving value and fields from an extension string
    
    """
    @staticmethod
    def register(spark: SparkSession):
        """
        Summary:
            Register extension parser udf
        Args:
            spark (SparkSession): spark session to access resources/files/load dataframes
        """
        def __check_udf_registered(udf_name: str) -> bool:
            """
            Check if UDF is registered in spark session
            """
            return udf_name in [func.name for func in spark.catalog.listFunctions()]
        
        if not __check_udf_registered(GlobalConstants.PARSE_EXTENSION_UDF):
            spark.udf.register(
                GlobalConstants.PARSE_EXTENSION_UDF, ExtensionParser.parse_extension, T.StringType())
        
    @staticmethod
    def parse_extension(extension_str: str, urlList_str: str, value: str, fields: str) -> str:
        """
        Parses json string extension object and retrieves target url, value and field from extension object
        Args:
            extension_str (str): json string representing the extension
            urlList_str (str): comma delimited string of url's to retrieve from extension
            value (str): value key to retrieve from extension object
            fields (str): comma delimited field(s) from value to retrieve (concatenated with '<->')

        Returns:
            str: retrieve value and field from extension object
        """
        if extension_str and urlList_str:
            urlList = urlList_str.split(',')
            extension_arr = json.loads(extension_str)
            nested_extension_value = ExtensionParser.get_nested_extension_value(extension_arr, urlList, value)
            return ExtensionParser.concat_fields(nested_extension_value, fields)
        else:
            return None

    @staticmethod
    def get_nested_extension_value(extension_arr: list, urlList: list, value: str) -> str:
        """
        Summary:
            Retrieve nested values as indicated by urlList (each comma delimited url is another level (depth))
        Args:
            extension_arr (list): list of extension objects
            urlList (list): list of urls to retreive (Every url here is an additional depth level)
            value (str): value key to retrieve from extension object

        Returns:
            str: Retrieve value from nexted extension level
        """
        url = urlList.pop(0)
        extension = next((ext for ext in extension_arr if ext.get('url') == url), None)
        if (extension != None):
            if len(urlList) != 0 and isinstance(extension, dict):
                return ExtensionParser.get_nested_extension_value(extension.get('extension', []), urlList, value)
            else:
                return extension.get(value)
        else:
            return extension

    @staticmethod
    def concat_fields(extension_value_obj: dict, fields_list_str: str) -> str:
        """
        Summary:
            Retrieve field(s) from nested extension value object. If multiple fields are indicated, return concatenated with '<->'
        Args:
            extension_value_obj (dict): nested extension object value(value at last level url)
            fields_list_str (str): comma delimited list of fields to retrieve

        Returns:
            str: retrieve field from extension value object 
        """
        if fields_list_str == '' or extension_value_obj is None or not isinstance(extension_value_obj, dict):
            return extension_value_obj
        fields_list = fields_list_str.split(",")
        field_values = [extension_value_obj[field] for field in fields_list]
        return '<->'.join(field_values)