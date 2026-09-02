from dataclasses import dataclass

from pyspark.sql import DataFrame

from dmf.model.source_configuration import MappingDefinition


@dataclass(eq=True, frozen=True)
class IdMappingInfo:
    source_df: DataFrame
    mapping_definition: MappingDefinition
