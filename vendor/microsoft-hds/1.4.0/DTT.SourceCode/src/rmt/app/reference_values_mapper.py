from pyspark.sql import SparkSession

import rmt.core.logger as logger
from rmt.app.common.values_mapper import ValuesMapper
from rmt.core.values_mapping.mapping_definitions_reader import MappingDefinitionsReader
from rmt.core.values_mapping.mapping_writer import MappingWriter


class ReferenceValuesMapper:
    @staticmethod
    def create_reference_values_mapping(
        spark: SparkSession,
        source_domain: str,
        mapping_definitions_reader: MappingDefinitionsReader,
        mapping_file_output_path: str,
        number_of_partition_files=-1,
    ):
        logger.info(
            f"""source_domain={source_domain},
            mapping definitions sources={mapping_definitions_reader.sources},
            mapping_file_output_path={mapping_file_output_path}, number_of_partition_files={number_of_partition_files}"""
        )

        if number_of_partition_files <= 0 and number_of_partition_files != -1:
            message = "Number of partitions must be either greater than 0, or equal to -1"
            raise ValueError(message)

        mapping_dataframe = ValuesMapper.create_and_validate_reference_values_mapping(spark, source_domain, mapping_definitions_reader)

        logger.info("Writing mapping dataframe")
        MappingWriter.overwrite(
            mapping_dataframe,
            mapping_file_output_path,
            number_of_partition_files,
        )
