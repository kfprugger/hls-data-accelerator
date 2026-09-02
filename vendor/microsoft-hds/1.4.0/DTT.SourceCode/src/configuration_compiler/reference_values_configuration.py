from collections import defaultdict
from typing import Dict, List, Tuple

from configuration_compiler.column_transformation.reference_columns_mapping_parser import ReferenceColumnsMappingParser
from configuration_compiler.config_files_models.adapter.ext_model import AdapterModel
from configuration_compiler.config_files_models.env.ext_model import EnvConfigModel
from configuration_compiler.spec_models.target_table_schema import TargetTableSchemaExt
from common.model.types import DataSourceId
from dmf.model.reference_values_configuration import ReferenceValuesConfiguration
from common.model.source_to_reference_mapping import SourceToReferenceMapping


def from_configuration(
    dmf_adaptor: AdapterModel,
    target_tables_schemas: dict[DataSourceId, TargetTableSchemaExt],
    env_config: EnvConfigModel,
) -> Tuple[ReferenceValuesConfiguration, Dict[DataSourceId, List[SourceToReferenceMapping]]]:
    reference_columns_mappings = ReferenceColumnsMappingParser.parse_reference_column_mappings(
        dmf_adaptor, target_tables_schemas
    )
    source_to_reference_mappings = defaultdict(list)
    for source_id, source_column_mappings in reference_columns_mappings.items():
        for source_field_mappings in source_column_mappings.values():
            for target_column_mappings in source_field_mappings.values():
                # take only first as we care only about any source to reference mapping
                # (there might be multiple targets for same source mapping)
                target_column_mapping = target_column_mappings[0]
                source_to_reference_mappings[source_id].append(
                    SourceToReferenceMapping(
                        source_field_name=target_column_mapping.original_source_field_name,
                        target_reference_table_name=target_column_mapping.transformation_target_id,
                        target_reference_field_name=target_column_mapping.target_field_name,
                    )
                )

    return ReferenceValuesConfiguration(
        source_domain=dmf_adaptor.sourceDomain,
        default_value=dmf_adaptor.defaultReferenceValue,
        fail_upon_missing_reference_values=dmf_adaptor.failUponMissingReferenceValues,
        secondary_lake_location=env_config.secondary_lake_location,
    ), dict(source_to_reference_mappings)


def get_source_to_reference_mappings(
    source_to_reference_mappings: Dict[DataSourceId, List[SourceToReferenceMapping]], source_id: str
) -> list[SourceToReferenceMapping]:
    return source_to_reference_mappings.get(source_id, [])
