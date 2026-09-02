# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
import hashlib
from typing import Union
from pyspark.sql import functions as F, DataFrame
from pyspark.sql.types import Row, TimestampType, ArrayType, StructType
from pyspark.sql.types import StringType, Row, BooleanType, TimestampType
from microsoft.fabric.hls.hds.flatten.constants import FlattenConstants as C
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.flatten.normalization.utils import NormalizationUtils

class IdentifierNormalization:
    @staticmethod
    def normalize_url(link_str: str) -> Union[str,None]:
        """
        Normalization of the url
        """
        if not isinstance(link_str, str) or link_str is None:
            return None
        
        link_encoded = link_str.encode()
        hash_object = hashlib.sha256(link_encoded)
        return hash_object.hexdigest()

    @staticmethod
    def normalize_resource_id(id_value: str,
                              type_value: str,
                              base_url: Union[str, None] = None
                              ) -> Union[str,None]:
        """
        Resource/reference id normalization. 
        """
        
        if id_value is None or type_value is None:
            return None
        
        full_url = type_value + '/' + id_value
        if base_url:
            base_url = NormalizationUtils.remove_url_scheme_regex(base_url)
            full_url = base_url + '/' + full_url

        return IdentifierNormalization.normalize_url(full_url)

    @staticmethod 
    def source_id_identifier_exists_in_row(identifier_row: Row, source_id_code: str) -> bool:
        """
        Check if a specific source_id_code exists in the Identifier Row.
        
        Args:
            identifier_row: The Row object representing the Identifier struct.
            source_id_code: The code to check for.
            
        Returns:
            bool: True if the source_id_code exists, False otherwise.
        """
        # Check if the 'type' field exists and is not null
        identifier_type = NormalizationUtils.get_row_field(identifier_row, 'type')
        if identifier_type is None:
            return False

        # Check if the 'coding' field exists and is a list
        coding_list = NormalizationUtils.get_row_field(identifier_type, 'coding', cast_type=list)
        if coding_list is None:
            return False

        # Iterate through the coding list to check for the source_id_code
        for coding in coding_list:
            code = NormalizationUtils.get_row_field(coding, 'code', cast_type=str)
            if code == source_id_code:
                return True

        return False
    
    @staticmethod
    def add_source_id_to_identifier_row(identifier: Row, value: str, system: str) -> Row:
        """
        This function is used to normalize the 'fhirId' in the Identifier struct.
        Adds the 'fhirId' (or any source ID code) to the 'coding' array of the 'type' field in a single Identifier struct
        if it doesn't exist. 
        
        Args:
            identifier: The Row object representing the 'identifier' struct.
            value: The value of the source ID (e.g., 'fhirId') to be added.
            source_system: The source system associated with the identifier.
        
        Returns:
            Row: Updated identifier struct with the source_id_code added if it didn't already exist.
        """
        identifier = IdentifierNormalization.conform_to_row_identifier_schema(identifier)
        
        # Check if the source_id_code already exists in the identifier's 'coding' array
        if IdentifierNormalization.source_id_identifier_exists_in_row(identifier, "fhirId"):
            return identifier
        
        
        identifier_value = NormalizationUtils.get_row_field(identifier, 'value', None)
        identifier_system = NormalizationUtils.get_row_field(identifier, 'system', None)
        # If either the identifier value or system is already set, we do nothing
        if identifier_value or identifier_system:
            return identifier

        # Predefined Row for FHIR ID coding
        new_coding = Row(
                extension=None,
                id=None,
                system=C.FHIR_IDENTIFIER_TYPE_CODING_SYSTEM_URL,  # System for FHIR Id
                version=None,
                code=C.FHIR_IDENTIFIER_TYPE_CODING_CODE,  # The code to add
                display=C.FHIR_IDENTIFIER_TYPE_CODING_DISPLAY,
                userSelected=None
            )

        # Get the 'type' field in the identifier
        identifier_type = NormalizationUtils.get_row_field(identifier, 'type')

        if identifier_type:
            # Get the 'coding' array within the 'type' field
            coding_array = NormalizationUtils.get_row_field(identifier_type, 'coding', [])
            
            coding_array.append(new_coding)

            # Update the 'type' field with the new 'coding' array
            updated_type = Row(
                extension=NormalizationUtils.get_row_field(identifier_type, 'extension', None),
                id=NormalizationUtils.get_row_field(identifier_type, 'id', None),
                coding=coding_array,
                text=NormalizationUtils.get_row_field(identifier_type, 'text', None)
            )
        else:
            # If no 'type' field exists, create it with the source ID
            updated_type = Row(
                extension=None,
                id=None,
                coding=[new_coding],
                text=C.FHIR_IDENTIFIER_TYPE_TEXT
            )

        # Return the updated identifier struct with the new 'type' field
        return Row(
            extension=NormalizationUtils.get_row_field(identifier, 'extension', None),
            use=NormalizationUtils.get_row_field(identifier, 'use', None),
            value=value,  # Set the ID value here
            system=system,  # Set the source system here
            type=updated_type,
            period=NormalizationUtils.get_row_field(identifier, 'period', {}),
            assigner=NormalizationUtils.get_row_field(identifier, 'assigner', {})
        )

    @staticmethod
    def conform_to_row_identifier_schema(row: Row) -> Row:
        """
        Ensures that a single Identifier row conforms to the expected schema by explicitly casting fields.
        If fields are missing or non-conforming, they will be cast to null.
        This version ensures strict schema and nullability alignment for a single row and safely handles nested fields.
        
        Args:
            row: The Row object representing an Identifier.
            
        Returns:
            Row: The Row object that conforms to the expected Identifier schema.
        """

        # Process the 'type' field with its nested structure conforming to CODEABLE_CONCEPT_SCHEMA
        identifier_type = NormalizationUtils.get_row_field(row, 'type')
        
        if isinstance(identifier_type, str):
            identifier_type = NormalizationUtils.create_row_from_string(identifier_type, C.CODEABLE_CONCEPT_SCHEMA)
        
        if identifier_type:
            identifier_coding = [Row(
                extension=NormalizationUtils.get_row_field(c, 'extension', cast_type=str),
                id=NormalizationUtils.get_row_field(c, 'id', cast_type=str),
                system=NormalizationUtils.get_row_field(c, 'system', cast_type=str),
                version=NormalizationUtils.get_row_field(c, 'version', cast_type=str),
                code=NormalizationUtils.get_row_field(c, 'code', cast_type=str),
                display=NormalizationUtils.get_row_field(c, 'display', cast_type=str),
                userSelected=NormalizationUtils.get_row_field(c, 'userSelected', default=None, cast_type=bool)  # Boolean field
            ) for c in NormalizationUtils.get_row_field(identifier_type, 'coding', [])]
            identifier_type_struct = Row(
                extension=NormalizationUtils.get_row_field(identifier_type, 'extension', cast_type=str),
                id=NormalizationUtils.get_row_field(identifier_type, 'id', cast_type=str),
                coding=identifier_coding,
                text=NormalizationUtils.get_row_field(identifier_type, 'text', cast_type=str)
            )
        else:
            identifier_type_struct = {}

        # Process the 'period' field with its nested structure conforming to PERIOD_SCHEMA
        identifier_period = NormalizationUtils.get_row_field(row, 'period')
        if identifier_period:
            identifier_period_struct = Row(
                extension=NormalizationUtils.get_row_field(identifier_period, 'extension', cast_type=str),
                id=NormalizationUtils.get_row_field(identifier_period, 'id', cast_type=str),
                start=NormalizationUtils.get_row_field(identifier_period, 'start', cast_type=lambda x: TimestampType().fromInternal(x)),  # Cast to Timestamp
                end=NormalizationUtils.get_row_field(identifier_period, 'end', cast_type=lambda x: TimestampType().fromInternal(x))      # Cast to Timestamp
            )
        else:
            identifier_period_struct = {}

        # Process the 'assigner' field with its nested identifier structure conforming to IDENTIFIER_REFERENCE_SCHEMA
        identifier_assigner = NormalizationUtils.get_row_field(row, 'assigner')
        if identifier_assigner:
            assigner_identifier = NormalizationUtils.get_row_field(identifier_assigner, 'identifier')
            if assigner_identifier:
                assigner_identifier_struct = Row(
                    extension=NormalizationUtils.get_row_field(assigner_identifier, 'extension', cast_type=str),
                    use=NormalizationUtils.get_row_field(assigner_identifier, 'use', cast_type=str),
                    type=NormalizationUtils.get_row_field(assigner_identifier, 'type', cast_type=str),
                    value=NormalizationUtils.get_row_field(assigner_identifier, 'value', cast_type=str),
                    system=NormalizationUtils.get_row_field(assigner_identifier, 'system', cast_type=str),
                    period=NormalizationUtils.get_row_field(assigner_identifier, 'period', cast_type=str),
                    assigner=NormalizationUtils.get_row_field(assigner_identifier, 'assigner', cast_type=str)
                )
            else:
                assigner_identifier_struct = {}

            identifier_assigner_struct = Row(
                extension=NormalizationUtils.get_row_field(identifier_assigner, 'extension', cast_type=str),
                id=NormalizationUtils.get_row_field(identifier_assigner, 'id', cast_type=str),
                reference=NormalizationUtils.get_row_field(identifier_assigner, 'reference', cast_type=str),
                type=NormalizationUtils.get_row_field(identifier_assigner, 'type', cast_type=str),
                identifier=assigner_identifier_struct,
                display=NormalizationUtils.get_row_field(identifier_assigner, 'display', cast_type=str)
            )
        else:
            identifier_assigner_struct = {}

        # Return the final Row, with fields that conform to the expected schema and casting applied
        return Row(
            extension=NormalizationUtils.get_row_field(row, 'extension', cast_type=str),
            use=NormalizationUtils.get_row_field(row, 'use', cast_type=str),
            value=NormalizationUtils.get_row_field(row, 'value', cast_type=str),
            system=NormalizationUtils.get_row_field(row, 'system', cast_type=str),
            type=identifier_type_struct,
            period=identifier_period_struct,
            assigner=identifier_assigner_struct
        )
    
    @staticmethod
    def source_id_identifier_exists_in_col(df: DataFrame, identifier_column: str, source_id_code: str = C.FHIR_IDENTIFIER_TYPE_CODING_CODE) -> DataFrame:
        """
        Optimized check for 'fhirId' in the identifier array using PySpark SQL functions.
        
        Args:
            df: The DataFrame containing the 'identifier' column as an array of struct.
            identifier_column: The column containing the identifiers array.
            source_id_code: The code to check for (default is 'fhirId').
            
        Returns:
            DataFrame: The same DataFrame with an additional column 'source_id_identifier_exists', which is True if fhirId exists.
        """
        if identifier_column not in df.columns:
            # Return the DataFrame with source_id_identifier_exists set to False if no identifier column
            return df.withColumn("source_id_identifier_exists", F.lit(False))

        # Null-safe check for each level of nesting in the identifier array
        return df.withColumn(
            "source_id_identifier_exists",
            F.when(
                F.col(identifier_column).isNull(), F.lit(False)  # If the identifier column is null, set to False
            ).otherwise(
                # Use `exists` with null checks for each nested field to ensure they are not null before comparison
                F.expr(f"""
                    exists({identifier_column}, x -> 
                        x.type is not null and 
                        exists(x.type.coding, c -> c.code is not null and c.code = '{source_id_code}')
                    )
                """)
            )
        )

    @staticmethod
    def add_source_id_to_identifier_col(df: DataFrame, identifier_column: str, id_column: str, source_system_column: str) -> DataFrame:
        """
        SQL-based approach to add 'fhirId' identifier if it does not exist, ensuring it matches the existing identifier schema.

        Args:
            df: The DataFrame containing the 'identifier' column as an array of struct.
            identifier_column: The column containing the identifiers array.
            id_column: The column containing the source Id value.
            source_system_column: The column containing the source system value.

        Returns:
            DataFrame: The DataFrame with updated identifiers where fhirId is added if it doesn't exist.
        """

        # Ensure we handle the case where the identifier array may be missing or empty
        df = df.withColumn(
            identifier_column,
            F.when(
                F.col(identifier_column).isNull(), F.array().cast(C.NORM_IDENTIFIER_ARRAY_SCHEMA)
            ).otherwise(F.col(identifier_column))
        )

        return df.withColumn(
            identifier_column,
            F.when(
                F.col("source_id_identifier_exists") == False,
                F.array_union(
                    F.col(identifier_column),
                    F.array(F.struct(
                        F.lit(None).cast(StringType()).alias('extension'),
                        F.lit(None).cast(StringType()).alias('use'),
                        F.col(id_column).cast(StringType()).alias('value'),
                        F.col(source_system_column).cast(StringType()).alias('system'),
                        F.struct(
                            F.lit(None).cast(StringType()).alias('extension'),
                            F.lit(None).cast(StringType()).alias('id'),
                            F.array(F.struct(
                                F.lit(None).cast(StringType()).alias('extension'),
                                F.lit(None).cast(StringType()).alias('id'),
                                F.lit(C.FHIR_IDENTIFIER_TYPE_CODING_SYSTEM_URL).cast(StringType()).alias('system'),
                                F.lit(None).cast(StringType()).alias('version'),
                                F.lit(C.FHIR_IDENTIFIER_TYPE_CODING_CODE).cast(StringType()).alias('code'),
                                F.lit(C.FHIR_IDENTIFIER_TYPE_TEXT).cast(StringType()).alias('display'),
                                F.lit(None).cast(BooleanType()).alias('userSelected')
                            )).alias('coding'),
                            F.lit(C.FHIR_IDENTIFIER_TYPE_TEXT).cast(StringType()).alias('text')
                        ).alias('type'),
                        F.struct(
                            F.lit(None).cast(StringType()).alias('extension'),
                            F.lit(None).cast(StringType()).alias('id'),
                            F.lit(None).cast(TimestampType()).alias('start'),
                            F.lit(None).cast(TimestampType()).alias('end')
                        ).alias('period'),
                        F.struct(
                            F.lit(None).cast(StringType()).alias('extension'),
                            F.lit(None).cast(StringType()).alias('id'),
                            F.lit(None).cast(StringType()).alias('reference'),
                            F.lit(None).cast(StringType()).alias('type'),
                            F.struct(
                                F.lit(None).cast(StringType()).alias('extension'),
                                F.lit(None).cast(StringType()).alias('use'),
                                F.lit(None).cast(StringType()).alias('type'),
                                F.lit(None).cast(StringType()).alias('value'),
                                F.lit(None).cast(StringType()).alias('system'),
                                F.lit(None).cast(StringType()).alias('period'),
                                F.lit(None).cast(StringType()).alias('assigner')
                            ).alias('identifier'),
                            F.lit(None).cast(StringType()).alias('display')
                        ).alias('assigner')
                    ))
                )
            ).otherwise(F.col(identifier_column))
        )
    
    @staticmethod
    def conform_to_col_identifier_schema(df: DataFrame, identifier_column: str) -> DataFrame:
        """
        Ensures that all identifiers conform to the expected schema by explicitly casting fields.
        If fields are missing or non-conforming, they will be cast to null.
        This version ensures strict schema and nullability alignment.
        
        Args:
            df: The DataFrame containing the 'identifier' column as an array of structs.
            identifier_column: The column containing the identifiers array.
            
        Returns:
            DataFrame: The DataFrame with identifiers that conform to the expected schema, 
                    with non-existing fields cast to null and matching the target schema.
        """
        
        # Transforming each identifier field to conform to the schema
        transformed_df = df.withColumn(
            identifier_column,
            F.transform(
                F.when(F.col(identifier_column).isNotNull(), F.col(identifier_column))
                .otherwise(F.array()),  # Empty array instead of null
                lambda x: F.struct(
                    F.coalesce(x.getField("extension"), F.lit(None).cast("string")).alias("extension"),
                    F.coalesce(x.getField("use"), F.lit(None).cast("string")).alias("use"),
                    F.coalesce(x.getField("value"), F.lit(None).cast("string")).alias("value"),
                    F.coalesce(x.getField("system"), F.lit(None).cast("string")).alias("system"),
                    F.when(
                        x.getField("type").isNotNull(),
                        F.struct(
                            F.coalesce(x.getField("type").getField("extension"), F.lit(None).cast("string")).alias("extension"),
                            F.coalesce(x.getField("type").getField("id"), F.lit(None).cast("string")).alias("id"),
                            F.transform(
                                F.coalesce(x.getField("type").getField("coding"), F.array()),
                                lambda c: F.struct(
                                    F.coalesce(c.getField("extension"), F.lit(None).cast("string")).alias("extension"),
                                    F.coalesce(c.getField("id"), F.lit(None).cast("string")).alias("id"),
                                    F.coalesce(c.getField("system"), F.lit(None).cast("string")).alias("system"),
                                    F.coalesce(c.getField("version"), F.lit(None).cast("string")).alias("version"),
                                    F.coalesce(c.getField("code"), F.lit(None).cast("string")).alias("code"),
                                    F.coalesce(c.getField("display"), F.lit(None).cast("string")).alias("display"),
                                    F.coalesce(c.getField("userSelected"), F.lit(None).cast("boolean")).alias("userSelected")
                                )
                            ).alias("coding"),
                            F.coalesce(x.getField("type").getField("text"), F.lit(None).cast("string")).alias("text")
                        )
                    ).alias("type"),
                    F.when(
                        x.getField("period").isNotNull(),
                        F.struct(
                            F.coalesce(x.getField("period").getField("extension"), F.lit(None).cast("string")).alias("extension"),
                            F.coalesce(x.getField("period").getField("id"), F.lit(None).cast("string")).alias("id"),
                            F.coalesce(x.getField("period").getField("start"), F.lit(None).cast("timestamp")).alias("start"),
                            F.coalesce(x.getField("period").getField("end"), F.lit(None).cast("timestamp")).alias("end")
                        )
                    ).alias("period"),
                    F.when(
                        x.getField("assigner").isNotNull(),
                        F.struct(
                            F.coalesce(x.getField("assigner").getField("extension"), F.lit(None).cast("string")).alias("extension"),
                            F.coalesce(x.getField("assigner").getField("id"), F.lit(None).cast("string")).alias("id"),
                            F.coalesce(x.getField("assigner").getField("reference"), F.lit(None).cast("string")).alias("reference"),
                            F.coalesce(x.getField("assigner").getField("type"), F.lit(None).cast("string")).alias("type"),
                            F.struct(
                                F.coalesce(x.getField("assigner").getField("identifier").getField("extension"), F.lit(None).cast("string")).alias("extension"),
                                F.coalesce(x.getField("assigner").getField("identifier").getField("use"), F.lit(None).cast("string")).alias("use"),
                                F.coalesce(x.getField("assigner").getField("identifier").getField("type"), F.lit(None).cast("string")).alias("type"),
                                F.coalesce(x.getField("assigner").getField("identifier").getField("value"), F.lit(None).cast("string")).alias("value"),
                                F.coalesce(x.getField("assigner").getField("identifier").getField("system"), F.lit(None).cast("string")).alias("system"),
                                F.coalesce(x.getField("assigner").getField("identifier").getField("period"), F.lit(None).cast("string")).alias("period"),
                                F.coalesce(x.getField("assigner").getField("identifier").getField("assigner"), F.lit(None).cast("string")).alias("assigner")
                            ).alias("identifier"),
                            F.coalesce(x.getField("assigner").getField("display"), F.lit(None).cast("string")).alias("display")
                        )
                    ).alias("assigner")
                )
            )
        )
    
        # Ensure the entire column conforms to the schema by casting to the expected schema
        return transformed_df.withColumn(identifier_column, F.col(identifier_column).cast(C.NORM_IDENTIFIER_ARRAY_SCHEMA))

    @staticmethod
    def normalize_resource_identifier(df: DataFrame, identifier_column: str, id_column: str, source_system_column: str) -> DataFrame:
        """
        Normalizes FHIR resource identifiers by ensuring the 'fhirId' is added if missing. 
        If the identifier column does not exist, it is added with the 'fhirId' identifier.
        
        Args:
            df: The DataFrame containing the 'identifier' column as an array of struct.
            identifier_column: The column containing the identifiers array.
            id_column: The column containing the source Id value.
            source_system_column: The column containing the source system value.
            
        Returns:
            DataFrame: The DataFrame with normalized identifiers and other columns removed.
        """
        
        if identifier_column not in df.columns:
            error_message = LC.MISSING_RESOURCE_IDENTIFIER_COLUMN_ERR_MSG.format(identifier_column=identifier_column)
            raise ValueError(error_message)
        
        if source_system_column not in df.columns:
            error_message = LC.MISSING_SOURCE_SYSTEM_COLUMN_ERROR_MSG.format(source_system_column=source_system_column)
            raise ValueError(error_message)
        
        if id_column not in df.columns:
            error_message = LC.MISSING_RESOURCE_ID_COLUMN_ERROR_MSG.format(resource_id_column=id_column)
            raise ValueError(error_message)
        
        def validate_identifier_schema(df, schema_type):
            expected_schema = C.NORM_IDENTIFIER_ARRAY_SCHEMA if schema_type == 'array' else C.NORM_IDENTIFIER_SCHEMA
            if not NormalizationUtils.is_schema_matching(actual_schema, expected_schema):
                error_message = LC.INVALID_RESOURCE_IDENTIFIER_SCHEMA_ERR_MSG.format(
                    identifier_column=identifier_column,
                    expected_schema=expected_schema,
                    actual_schema=actual_schema
                )
                raise ValueError(error_message)
            return df

        # Get the schema type of the identifier column
        actual_schema = df.schema[identifier_column].dataType
        
        # Determine schema type (array or struct)
        schema_type = 'array' if isinstance(actual_schema, ArrayType) else 'struct' if isinstance(actual_schema, StructType) else None
        
        df = validate_identifier_schema(df, schema_type)
        
        if schema_type:
            # Copy original Identifier column
            df = df.withColumn(
                identifier_column + C.NORM_COPY_POSTFIX,
                F.col(identifier_column)
            )
        
        original_columns = df.columns
        
        # Handle normalization based on schema type
        if schema_type == 'array':
            df = IdentifierNormalization.conform_to_col_identifier_schema(df, identifier_column=identifier_column)
            
            df_with_fhir_id_check = IdentifierNormalization.source_id_identifier_exists_in_col(df, identifier_column=identifier_column)

            df_normalized = IdentifierNormalization.add_source_id_to_identifier_col(
                df_with_fhir_id_check, 
                identifier_column=identifier_column, 
                id_column=id_column, 
                source_system_column=source_system_column
            )
        elif schema_type == 'struct':
            add_source_id_to_identifier_row_udf = F.udf(
                lambda identifier, value, system: IdentifierNormalization.add_source_id_to_identifier_row(identifier, value, system), 
                C.NORM_IDENTIFIER_SCHEMA
            )
            df_normalized = df.withColumn(
                identifier_column, 
                add_source_id_to_identifier_row_udf(F.col(identifier_column), F.col(id_column), F.col(source_system_column))
            )
        
        # Return DataFrame with original columns
        return df_normalized.select(*original_columns)