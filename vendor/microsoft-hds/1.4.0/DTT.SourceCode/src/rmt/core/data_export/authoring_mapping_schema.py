from pyspark.sql.types import StringType, StructField, StructType

from rmt.file_model.data_management.authoring_files_constants import (AUTHORING_CONTRIBUTOR_COLUMN_NAME, AUTHORING_SOURCE_VALUE_COLUMN_NAME, AUTHORING_TABLE_COLUMN_NAME,
                                                                      AUTHORING_TARGET_ID_COLUMN_NAME)


class AuthoringMappingSchema:
    CONTRIBUTOR = AUTHORING_CONTRIBUTOR_COLUMN_NAME
    TABLE = AUTHORING_TABLE_COLUMN_NAME
    SOURCE_VALUE = AUTHORING_SOURCE_VALUE_COLUMN_NAME
    TARGET_ID = AUTHORING_TARGET_ID_COLUMN_NAME

    schema = StructType(
        [
            StructField(CONTRIBUTOR, StringType(), False),
            StructField(TABLE, StringType(), False),
            StructField(SOURCE_VALUE, StringType(), False),
            StructField(TARGET_ID, StringType(), False),
        ]
    )
