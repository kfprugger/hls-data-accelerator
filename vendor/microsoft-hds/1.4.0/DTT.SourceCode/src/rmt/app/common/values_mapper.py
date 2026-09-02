from pyspark.sql import DataFrame, SparkSession

import rmt.core.logger as logger
from rmt.core.values_mapping.mapping_adder import MappingAdder
from rmt.core.values_mapping.mapping_creator import MappingCreator
from rmt.core.values_mapping.mapping_definitions_reader import MappingDefinitionsReader
from rmt.core.values_mapping.mapping_schema import MappingSchema
from rmt.core.values_mapping.mapping_validator import MappingValidator


class ValuesMapper:
    @staticmethod
    def create_and_validate_reference_values_mapping(
        spark: SparkSession,
        source_domain: str,
        mapping_definitions_reader: MappingDefinitionsReader,
    ) -> DataFrame:

        mapping_dataframe = spark.createDataFrame([], MappingSchema.schema)

        logger.info("Reading mapping definitions and creating mapping dataframe")

        for source in mapping_definitions_reader.sources:
            mapping_definitions = mapping_definitions_reader.read(source)
            MappingValidator.validate_mapping_for_source(source, mapping_definitions)
            mapping_source = MappingCreator.create(spark, source_domain, mapping_definitions)
            # mapping change since we don't support overriding of mappings anymore
            # this line below was changed from mapping_dataframe = MappingAdder.add_source(mapping_dataframe, mapping_source)
            mapping_dataframe = MappingAdder.add(mapping_dataframe, mapping_source)

        logger.info("Validating mapping dataframe")
        mapping_dataframe = MappingValidator.validate(mapping_dataframe)

        return mapping_dataframe
