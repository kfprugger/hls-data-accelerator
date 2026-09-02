from typing import List, Set

from common.utils.logging import Logger
from pyspark.sql import SparkSession

from common.model.data_access_definition import DataAccessDefinition, DataSourceTypeEnum
from dmf.transformations.model.transformation_types import TransformationMetaData
from common.reader.reader import Reader
from common.reader.reader_factory import ReaderFactory
from dmf.transformations.steps.partition_manager import PartitionManager
from dmf.transformations.writer.first_time_delta_storage_writer import FirstTimeDeltaStorageWriter
from dmf.transformations.writer.delta_table_upsert_writer import DeltaTableUpsertWriter


class WriterFactory:

    WRITER_SUPPORTED_FORMATS = ["delta"]

    @staticmethod
    def get_instance(data_access_definition: DataAccessDefinition, id, spark: SparkSession,
                     metadata: TransformationMetaData):
        WriterFactory._validate(data_access_definition, id, spark)

        if data_access_definition.data_source_type != DataSourceTypeEnum.STORAGE:
            raise ValueError(f"Target data source type '{data_access_definition.data_source_type}' is not supported")

        if data_access_definition.data_format not in WriterFactory.WRITER_SUPPORTED_FORMATS:
            raise ValueError(f"Target data format '{data_access_definition.data_format}' is not supported")

        reader: Reader = ReaderFactory.get_instance(data_access_definition)
        target_df = reader.read(spark)
        if not target_df:
            return FirstTimeDeltaStorageWriter(location=data_access_definition.data_source_owner_id, id=id)
        else:
            try:
                writable_column_names = WriterFactory._calc_writable_columns(metadata)
            except Exception as e:
                Logger.error(
                    f"Error while getting writable column names for table {data_access_definition.data_source_owner_id}. "
                    f"Context: {metadata}: {e}")
                raise
            return DeltaTableUpsertWriter(location=data_access_definition.data_source_owner_id, id=id,
                                          target_all_column_names=writable_column_names,
                                          target_key_column_names=metadata.target_key_col_names)

    @staticmethod
    def _calc_writable_columns(metadata: TransformationMetaData) -> List[str]:
        partition_columns = PartitionManager.get_partition_column_names(metadata.source_partitions_configs)
        all_writable_columns = (
            WriterFactory.source_to_target_mapped_columns(metadata) |
            set(metadata.target_key_col_names) |
            WriterFactory._id_mapped_columns(metadata) |
            metadata.synthetically_nulled_primary_keys |
            {metadata.target_period_start_col_name, metadata.target_period_end_col_name} |
            set(partition_columns)
            ) - set("")

        return list(all_writable_columns)

    @staticmethod
    def _id_mapped_columns(metadata: TransformationMetaData) -> Set[str]:
        return set([mapping.target_id_col_name for mapping in metadata.source_to_target_ids_mapping
                    if mapping.target_id_col_name in metadata.target_schema_col_names])

    @staticmethod
    def source_to_target_mapped_columns(metadata: TransformationMetaData) -> Set[str]:
        return set(item for sublist in metadata.source_to_target_col_names_mapping.values() for item in sublist)

    @staticmethod
    def _validate(data_access_definition: DataAccessDefinition, id, spark: SparkSession):
        if spark is None:
            raise ValueError("Spark session is required to create a writer instance")
        if id is None:
            raise ValueError("ID is required to create a writer instance")
        if data_access_definition.data_source_type != DataSourceTypeEnum.STORAGE:
            raise ValueError(f"Target data source type '{data_access_definition.data_source_type}' is not supported")
        if data_access_definition.data_source_owner_id is None:
            raise ValueError("DataAccessDefinition.data_source_owner_id is required to create a writer instance")
