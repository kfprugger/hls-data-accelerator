from pyspark.sql.types import StringType, StructField, StructType

from rmt.file_model.data_management.authoring_files_constants import (AUTHORING_CONTRIBUTOR_COLUMN_NAME, AUTHORING_ID_COLUMN_NAME, AUTHORING_TABLE_COLUMN_NAME,
                                                                      AUTHORING_VALUE_COLUMN_NAME)


class AuthoringDataSchema:
    CONTRIBUTOR = AUTHORING_CONTRIBUTOR_COLUMN_NAME
    TABLE = AUTHORING_TABLE_COLUMN_NAME
    VALUE = AUTHORING_VALUE_COLUMN_NAME
    ID = AUTHORING_ID_COLUMN_NAME

    schema = StructType(
        [
            StructField(CONTRIBUTOR, StringType(), False),
            StructField(TABLE, StringType(), False),
            StructField(VALUE, StringType(), False),
            StructField(ID, StringType(), False),
        ]
    )
