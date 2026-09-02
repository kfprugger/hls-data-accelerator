# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
from pyspark.sql import functions as F
from pyspark.sql.types import Row, ArrayType, StringType, StructType, StructField, Row
from microsoft.fabric.hls.hds.flatten.constants import FlattenConstants as C
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.flatten.normalization.utils import NormalizationUtils  
from microsoft.fabric.hls.hds.flatten.normalization.identifier_normalization import IdentifierNormalization 

class ReferenceNormalization:
    @staticmethod
    def normalize_ref_struct(reference_row: Row, source_system: str) -> Row:
        """
        Reference struct normalization
        
        Args:
        reference_row (Row): The input row representing a reference in a FHIR resource. 
                             It should have the fields 'reference', 'type', 'identifier', 'extension', 'display', id, and idOrig.

        Returns:
            Row: The normalized reference row.
        """
        
        if not source_system:
            error_message = LC.INVALID_REFERENCE_NORMALIZATION_SOURCE_SYSTEM_ERR_MSG.format(source_system=source_system)
            raise ValueError(error_message)

        # Default values for all fields 
        reference, type_, display, extension, id_, id_orig, reference_orig = None, None, None, None, None, None, None
        identifier = Row(extension=None,use=None,value=None, system=None, type=None, period=None, assigner=None)

        if not isinstance(reference_row, (Row, dict)):
            # Handle unexpected data type here
            return Row(reference=reference, 
                       type=type_, 
                       identifier=identifier, 
                       display=display, 
                       extension=extension, 
                       id=id_, 
                       idOrig=id_orig, 
                       msftSourceReference=reference_orig)
 
        if reference_row:
            reference = reference_row["reference"] if "reference" in reference_row else None
            type_ = reference_row["type"] if "type" in reference_row else None
            display = reference_row["display"] if "display" in reference_row else None
            extension = reference_row["extension"] if "extension" in reference_row else None
            
            reference_orig = reference
            
            # Handle identifier
            prev_identifier = reference_row["identifier"] if "identifier" in reference_row else {}
            if prev_identifier:
                if isinstance(prev_identifier, (Row, dict)):
                    # Handle the assigner field specially - it might be a JSON string from Avro schema
                    assigner_value = prev_identifier["assigner"] if "assigner" in prev_identifier else None
                    assigner_value = NormalizationUtils.parse_assigner_json_safely(assigner_value)
                    
                    identifier = Row(
                        extension=prev_identifier["extension"] if "extension" in prev_identifier else None,
                        use=prev_identifier["use"] if "use" in prev_identifier else None,
                        value=prev_identifier["value"] if "value" in prev_identifier else None,
                        system=prev_identifier["system"] if "system" in prev_identifier else None,
                        type=prev_identifier["type"] if "type" in prev_identifier else None,
                        period=prev_identifier["period"] if "period" in prev_identifier else None,
                        assigner=assigner_value
                    )
                elif isinstance(prev_identifier, (StringType, str)):
                    identifier = NormalizationUtils.create_row_from_string(prev_identifier, C.NORM_IDENTIFIER_SCHEMA)
            
            identifier = IdentifierNormalization.conform_to_row_identifier_schema(identifier)

            # Normalize only references with a `reference.reference` string
            if reference:
                reference_type, base_url, resource_type, resource_id, system, value = NormalizationUtils.get_reference_details(reference)
                type_ = type_ or resource_type
                if reference_type == "Literal":
                    # Normalize if (Patient/c088b7af-fc41-43cc-ab80-4a9ab8d47cd9) or 
                    # ('https://epic/Patient/c088b7af-fc41-43cc-ab80-4a9ab8d47cd9' and `sourceSystem=https://epic`)
                    if not base_url or NormalizationUtils.remove_url_scheme_regex(base_url) ==  NormalizationUtils.remove_url_scheme_regex(source_system):                  
                        base_url = source_system
                        id_ = IdentifierNormalization.normalize_resource_id(base_url=base_url,
                                                                         id_value=resource_id,
                                                                         type_value=type_)
                        id_orig = resource_id  # Preserve original id                                                                   
                        identifier = IdentifierNormalization.add_source_id_to_identifier_row(identifier, 
                                                                                      resource_id, 
                                                                                      base_url)                                            
                    # Do nothing if ('https://epic/Patient/c088b7af-fc41-43cc-ab80-4a9ab8d47cd9' and `sourceSystem=https://example.org/fhir`)
                    
                if reference_type == "Logical":
                    # Normalize Patient?identifier=99999, assuming sourceSystem is the same as the reference system
                    if not base_url and not system:
                        identifier = NormalizationUtils.create_identifier(identifier, value, source_system)
                    elif (NormalizationUtils.remove_url_scheme_regex(base_url) == NormalizationUtils.remove_url_scheme_regex(source_system)) or (not base_url and system):
                        # Normalize (https://epic/Patient?identifier=http://mrnsystem|99999 and sourceSystem=https://epic)
                        # or Patient?identifier=http://mrnsystem|99999
                        identifier = NormalizationUtils.create_identifier(identifier, value, system)
                        
                    # Do nothing if ('https://epic/Patient?identifier=http://mrnsystem|99999' and `sourceSystem=https://example.org/fhir`)
                    
                # Preserve original reference and clear reference
                reference_orig = reference
                reference = None

        return Row(reference=reference,
                   type=type_,
                   identifier=identifier,
                   display=display,
                   extension=extension,
                   id=id_,
                   idOrig=id_orig,
                   msftSourceReference=reference_orig)
    
    @staticmethod
    # Define a UDF that normalizes a column with nested references array
    def normalize_ref_array(column_data: list, source_system: str | None) -> list:
        """
        Nested reference array normalization udf
        """
        
        if column_data:
            return [ReferenceNormalization.normalize_ref_struct(row, source_system) for row in column_data]

        return column_data
    
    @staticmethod
    # Define a UDF that normalizes a specified nested references
    def normalize_nested_ref_struct_in_array(nested_ref_name: str, column_data: list, source_system: str | None) -> list:
        """
        Nested struct reference in an array normalization udf
        """
        if column_data:
            return [
                {
                    **(row if isinstance(row, dict) else row.asDict()),
                    **{nested_ref_name: ReferenceNormalization.normalize_ref_struct(row[nested_ref_name], source_system)}
                }
                for row in column_data
            ]
        return column_data
    
    @staticmethod
    def normalize_nested_ref_struct_in_struct(nested_ref_name: str, row: Row, source_system: str | None) -> Row:
        """
        Nested reference normalization for a StructType field
        """
        if row:
            row_dict = row if isinstance(row, dict) else row.asDict()

            # Normalize the nested_ref_name field
            nested_value = row_dict.get(nested_ref_name)
            normalized_value = ReferenceNormalization.normalize_ref_struct(nested_value, source_system)
            row_dict[nested_ref_name] = normalized_value

            # Convert the dictionary back to a Row object
            return Row(**row_dict)
        
        return row
    
    @staticmethod
    def normalize_nested_ref_array_in_struct(nested_ref_name: str, row: Row, source_system: str | None) -> Row:
        """
        Nested reference normalization for a ArrayType field
        """
        if row:
            row_dict = row if isinstance(row, dict) else row.asDict()
            
            # Normalize the nested_ref_name field
            nested_value = row_dict.get(nested_ref_name)
            normalized_value = ReferenceNormalization.normalize_ref_array(nested_value, source_system)
            row_dict[nested_ref_name] = normalized_value

            # Convert the dictionary back to a Row object
            return Row(**row_dict)
        
        return row
    
    @staticmethod
    # Define a UDF that normalizes a specified nested references
    def normalize_nested_ref_array_in_array(nested_ref_name: str, column_data: list, source_system: str | None) -> list:
        """
        Nested reference normalization udf
        """
        if column_data:
            return [
                {
                    **(row if isinstance(row, dict) else row.asDict()), 
                    **{nested_ref_name: ReferenceNormalization.normalize_ref_array(row[nested_ref_name], source_system)}
                }
                for row in column_data
            ]
        return column_data
    
    @staticmethod
    def create_normalize_nested_ref_udf(original_col_schema, nested_ref_name, nested_array):
        """
        Nested reference normalization dynamic udf
        """
        is_root_array_type = isinstance(original_col_schema, ArrayType)
        col_schema_fields = original_col_schema.elementType.fields if is_root_array_type else original_col_schema.fields

        field_name_to_index = {field.name: index for index, field in enumerate(col_schema_fields)}
        if nested_ref_name not in field_name_to_index:
            raise ValueError(LC.REFERENCE_NORMALIZATION_INVALID_CONFIG.format(nested_ref_name=nested_ref_name))

        nested_ref_index = field_name_to_index[nested_ref_name]
        extended_schema_fields = col_schema_fields[:]

        nested_ref_field_schema = C.NORM_REF_ARRAY_UDF_SCHEMA if nested_array else C.NORM_REF_STRUCT_UDF_SCHEMA
        extended_schema_fields[nested_ref_index] = StructField(nested_ref_name, nested_ref_field_schema, True)

        if is_root_array_type:
            extended_schema = ArrayType(StructType(extended_schema_fields), True)
            if nested_array:
                return F.udf(lambda column_data, source_system: ReferenceNormalization.normalize_nested_ref_array_in_array(nested_ref_name, column_data, source_system), extended_schema)
            return F.udf(lambda column_data, source_system: ReferenceNormalization.normalize_nested_ref_struct_in_array(nested_ref_name, column_data, source_system), extended_schema)

        extended_schema = StructType(extended_schema_fields)
        if nested_array:
            return F.udf(lambda column_data, source_system: ReferenceNormalization.normalize_nested_ref_array_in_struct(nested_ref_name, column_data, source_system), extended_schema)

        return F.udf(lambda column_data, source_system: ReferenceNormalization.normalize_nested_ref_struct_in_struct(nested_ref_name, column_data, source_system), extended_schema)
    