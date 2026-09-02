# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
import re
import json
from pyspark.sql import Row
from pyspark.sql.types import StructType, ArrayType, DataType
from microsoft.fabric.hls.hds.flatten.constants import FlattenConstants as C

class NormalizationUtils:
    
    @staticmethod
    def remove_url_scheme_regex(url: str):
        """
        Removes the scheme from a URL and ensures it does not end with '/'.

        This function uses a regular expression to remove the scheme (e.g., 'http://', 'https://') from a URL.
        If the URL is empty either before or after removing the scheme, the function returns None.

        Args:
            url (str): The URL from which to remove the scheme.

        Returns:
            str or None: The URL without the scheme, or None if the URL is empty.
        """
        if not isinstance(url, str) or not url:
            return None

        # Remove the scheme
        url = re.sub(r'^\w+://', '', url)

        # Ensure the URL does not end with '/'
        if url.endswith('/'):
            url = url[:-1]

        return url if url else None
    
    @staticmethod
    def get_reference_details(reference_string: str):
        """
        Normalization by reference string
        """
        # Check if the input is not a string
        if not isinstance(reference_string, str):
            return None, None, None, None, None, None

        # Try to match the literal reference pattern
        match_literal = C.REFERENCE_NORMALIZATION_PATTERN_LITERAL.search(reference_string)
        if match_literal:
            reference_type = "Literal"
            base_url = match_literal.group(1) or None
            resource_type = match_literal.group(4)
            resource_id = match_literal.group(5)
            system = None
            value = None
            return reference_type, base_url, resource_type, resource_id, system, value

        # Try to match the logical reference pattern
        match_logical = C.REFERENCE_NORMALIZATION_PATTERN_LOGICAL.search(reference_string)
        if match_logical:
            reference_type = "Logical"
            base_url = match_logical.group(1) or None
            resource_type = match_logical.group(4) 
            system = match_logical.group(5)  
            value = match_logical.group(6)  
            resource_id = None
            return reference_type, base_url, resource_type, resource_id, system, value

        # If no match, return None
        return None, None, None, None, None, None
    
    @staticmethod
    def create_row_from_string(data: str , schema: StructType) -> Row:
        """Create a Row object based on the provided schema."""
        data_dict = json.loads(data) if data else {}
        row_data = {}
        for field in schema:
            row_data[field.name] = data_dict.get(field.name, None)
        return Row(**row_data)
    
    @staticmethod
    def get_row_field(row, field, default=None, cast_type=None):
                """ 
                Safely get a field from the row, returns default if not present or null.
                Optionally cast the field to the specified cast_type (e.g., str, bool).
                """
                if not isinstance(row, (Row, dict)):
                    return default
                value = row[field] if field in row and row[field] is not None else default
                if cast_type and value is not None:
                    try:
                        value = cast_type(value)
                    except (ValueError, TypeError):
                        value = default
                return value

    @staticmethod
    def is_schema_matching(actual_schema: DataType, expected_schema: DataType) -> bool:
        """
        Check if the actual schema matches the expected schema.
        
        Args:
            actual_schema: The actual schema of the DataFrame column.
            expected_schema: The expected schema.
            
        Returns:
            bool: True if the schemas match, False otherwise.
        """
        def flatten_schema(schema: StructType, prefix: str = '') -> dict:
            """
            Flattens a Spark StructType schema into a dictionary for easier comparison.
            
            Args:
                schema (StructType): The schema to flatten.
                prefix (str): The prefix to add to the field names (used for nested fields).
                
            Returns:
                dict: A dictionary where the keys are the field names and the values are the data types.
            """
            fields = {}
            for field in schema.fields:
                field_name = prefix + field.name
                if isinstance(field.dataType, StructType):
                    fields.update(flatten_schema(field.dataType, prefix=field_name + "."))
                elif isinstance(field.dataType, ArrayType) and isinstance(field.dataType.elementType, StructType):
                    fields.update(flatten_schema(field.dataType.elementType, prefix=field_name + "."))
                else:
                    fields[field_name] = (field.dataType.simpleString(), field.nullable)
            return fields

        if isinstance(actual_schema, StructType) and isinstance(expected_schema, StructType):
            actual_schema_flat = flatten_schema(actual_schema)
            expected_schema_flat = flatten_schema(expected_schema)
            return actual_schema_flat == expected_schema_flat
        elif isinstance(actual_schema, ArrayType) and isinstance(expected_schema, ArrayType):
            return NormalizationUtils.is_schema_matching(actual_schema.elementType, expected_schema.elementType)
        else:
            return actual_schema == expected_schema
        
    @staticmethod
    def create_identifier(identifier, value, system):
        return Row(
            extension=identifier["extension"],
            use=identifier["use"],
            value=value,
            system=system,
            type=identifier["type"],
            period=identifier["period"],
            assigner=identifier["assigner"]
        )
    
    @staticmethod
    def parse_assigner_json_safely(assigner_value):
        """
        Safely parse assigner JSON strings while preventing infinite recursion.
        
        This method handles the common case where Avro schema serializes nested assigner 
        objects as JSON strings, causing data loss during normalization. It parses these
        JSON strings back into proper Row objects while preventing infinite recursion
        in deeply nested structures.
        
        Args:
            assigner_value: The assigner value that might be a JSON string
            
        Returns:
            Row: Parsed assigner Row object, or original value if parsing fails
        """
        if not (assigner_value and isinstance(assigner_value, str)):
            return assigner_value
            
        try:
            parsed_assigner = json.loads(assigner_value)
            if isinstance(parsed_assigner, dict):
                # Handle nested identifier safely to prevent infinite recursion
                nested_identifier = parsed_assigner.get("identifier")
                if nested_identifier and isinstance(nested_identifier, dict):
                    # Create a safe nested identifier without further assigner parsing
                    nested_identifier_row = Row(
                        extension=nested_identifier.get("extension"),
                        use=nested_identifier.get("use"),
                        value=nested_identifier.get("value"),
                        system=nested_identifier.get("system"),
                        type=nested_identifier.get("type"),
                        period=nested_identifier.get("period"),
                        assigner=nested_identifier.get("assigner")  # Keep as-is to prevent recursion
                    )
                else:
                    nested_identifier_row = nested_identifier  # Preserve original value
                
                return Row(
                    extension=parsed_assigner.get("extension"),
                    id=parsed_assigner.get("id"),
                    reference=parsed_assigner.get("reference"),
                    type=parsed_assigner.get("type"),
                    identifier=nested_identifier_row,  # Safely preserve nested data
                    display=parsed_assigner.get("display")
                )
        except (json.JSONDecodeError, TypeError, ValueError):
            # Return original value if any parsing error occurs
            pass
            
        return assigner_value
    