from pathlib import Path
from typing import Dict, List, Optional, Set
from configuration_compiler.configuration_content_wrapper import DttConfigurationContentWrapper

import configuration_compiler.configuration_compiler_helpers as cc_helpers
from configuration_compiler.column_transformation.columns_transformations_parser import ColumnsTransformationsParser
from configuration_compiler.column_transformation.proposed_paths_generator import (
    ProposedPathsGenerator,
    ProposedPathsResponse,
)
from configuration_compiler.column_transformation.source_modified_transformations_generator import (
    SourceModifiedTransformationsGenerator,
)
from configuration_compiler.common import Common
from configuration_compiler.ids_mapping_parser import IdsMappingParser
from configuration_compiler.config_files_models.adapter.ext_model import AdapterModel
from configuration_compiler.config_files_models.common.entity_definition_container import EntityDefinitionContainer
from configuration_compiler.config_files_models.db_schema.ext_model import DBSchemaModel
from configuration_compiler.config_files_models.db_schema_config.ext_model import DBConfigModel
from configuration_compiler.config_files_models.env.ext_model import EnvConfigModel
from configuration_compiler.config_files_models.semantics.ext_model import SemanticsModel
from configuration_compiler.config_files_models.semantics_config.ext_model import SemanticsConfigModel
from configuration_compiler.reference_values_configuration import (
    from_configuration,
    get_source_to_reference_mappings,
)
from configuration_compiler.source_configuration_factory import SourceConfigurationFactory
from configuration_compiler.source_tables_columns_config import parse_source_schema
from configuration_compiler.spec_models.target_table_schema import TargetTableSchemaExt
from configuration_compiler.validation.raw_config_validator import RawConfigValidator
from common.model.types import DataSourceId, TargetId
from dmf.model.data_feed_configuration import DataFeedConfiguration
from dmf.model.reference_values_configuration import ReferenceValuesConfiguration
from common.model.source_to_reference_mapping import SourceToReferenceMapping
from dmf.model.source_configuration import SourceConfiguration, SourceTableSchema
from dmf.model.target_configuration.target_transformation import ColumnTransformation
from dmf.model.validation.dmf_config_validator import DMFConfigValidator


class DataFeedConfigurationCompiler:
    @staticmethod
    def compile_configuration(config_content_wrapper: DttConfigurationContentWrapper) -> DataFeedConfiguration:
        adaptor: AdapterModel = AdapterModel.from_str(config_content_wrapper.adaptor_file_content)
        db_semantics: SemanticsModel = SemanticsModel.from_str(config_content_wrapper.target_db_semantics_content)
        if config_content_wrapper.target_db_semantics_content is not None:
            db_semantics_config: Optional[SemanticsConfigModel] = SemanticsConfigModel.from_str(
                config_content_wrapper.target_db_semantics_config_content
            )
        else:
            db_semantics_config: Optional[SemanticsConfigModel] = None
        db_schema: DBSchemaModel = DBSchemaModel.from_str(config_content_wrapper.target_db_schema_content)
        db_schema_config: DBConfigModel = DBConfigModel.from_str(config_content_wrapper.db_schema_config_content)
        env_config: EnvConfigModel = EnvConfigModel.from_str(config_content_wrapper.env_config_content)

        adapted_db_schema = db_schema_config.adapt_schema(db_schema, db_semantics)

        feed_id = adaptor.name

        source_entities_definition_container = EntityDefinitionContainer(
            name=cc_helpers.get_source_entities_container_name(adaptor, env_config),
            type=env_config.source_entities_container_type,
        )

        target_tables_schemas: dict[DataSourceId, TargetTableSchemaExt] = adapted_db_schema.parse_with_db_semantics(
            db_semantics
        )
        reference_values_configuration: ReferenceValuesConfiguration
        source_to_reference_mappings: Dict[DataSourceId, List[SourceToReferenceMapping]]
        reference_values_configuration, source_to_reference_mappings = from_configuration(
            adaptor, target_tables_schemas, env_config
        )
        RawConfigValidator(adaptor, target_tables_schemas).validate()

        source_schemas: dict[DataSourceId, SourceTableSchema] = parse_source_schema(adaptor)

        columns_transformations = ColumnsTransformationsParser(
            adaptor, target_tables_schemas
        ).parse_column_transformations()

        SourceModifiedTransformationsGenerator.add_transformations_for_all_target_tables(
            source_schemas,
            columns_transformations,
            feed_id,
            db_schema_config.configuration.modifiedOnTargetField,
            db_schema_config.configuration.sourceTableField,
        )
        columns_transformations = dict(columns_transformations)

        columns_transformations: dict[DataSourceId, dict[TargetId, Set[ColumnTransformation]]]

        source_configurations: Set[SourceConfiguration] = set()

        for query_table in adaptor.queryTables:
            query_table_name = query_table.name
            query_table_alias = query_table.alias
            data_access_definition = cc_helpers.generate_data_access_definition(
                env_config,
                source_entities_definition_container,
                query_table_name,
                query=None,
            )
            view_source_configuration = SourceConfigurationFactory.get_view_instance(
                query_table_name, feed_id, data_access_definition, query_table_alias
            )
            source_configurations.add(view_source_configuration)

        for source_table in adaptor.source_tables:
            data_access_definition = cc_helpers.generate_data_access_definition(
                env_config,
                source_entities_definition_container,
                source_table.tableName,
                query=source_table.query,
            )
            mapping_definitions = IdsMappingParser.parse_ids_mapping(
                columns_transformations[source_table.tableName],
                source_table,
                adapted_db_schema,
                env_config,
            )
            source_config = cc_helpers.generate_source_config(
                columns_transformations,
                feed_id,
                source_table.tableName,
                source_schemas,
                db_semantics_config,
                db_semantics.temporal_tables,
                target_tables_schemas,
                db_schema_config.configuration.modifiedOnTargetField,
                mapping_definitions,
                data_access_definition,
                env_config,
                frozenset(get_source_to_reference_mappings(source_to_reference_mappings, source_table.tableName)),
                db_schema_config.configuration.sourceTableField,
            )
            source_configurations.add(source_config)

        configuration = DataFeedConfiguration(
            feed_id=feed_id,
            source_configurations=frozenset(source_configurations),
            reference_values_configuration=reference_values_configuration,
        )
        DMFConfigValidator(configuration).validate()

        return configuration

    @staticmethod
    def get_proposed_paths(
        adaptor_file_location: Path,
        target_db_semantics_file_location: Path,
        target_db_schema_file_location: Path,
        db_schema_config_location: Path,
        source_table_name: str,
        source_field_name: str,
        target_table_name: str,
        target_field_name: str,
    ) -> ProposedPathsResponse:
        """
        This method is used to get the proposed paths for a given source and target field.
        It is used by the VsCode Extension UI to show the user the possible paths for a given field.
        Each path is a list of transformations that need to be applied to the source field to get the target field.
        In addition to the transformations, the path also contains the source and target table names. and some more metadata.
        For details about how the response is generated, please see the documentation of the ProposedPathsResponse class.
        For detailes about the final UI response body, please see the documentation of the Response class.
        """
        adaptor_str = Common.read_local_configuration_file(adaptor_file_location, True)
        target_db_semantics_str = Common.read_local_configuration_file(target_db_semantics_file_location, True)
        target_db_schema_str = Common.read_local_configuration_file(target_db_schema_file_location, True)
        db_schema_config_str = Common.read_local_configuration_file(db_schema_config_location, True)
        adaptor: AdapterModel = AdapterModel.from_str(adaptor_str)  # type: ignore
        db_semantics: SemanticsModel = SemanticsModel.from_str(target_db_semantics_str)  # type: ignore
        db_schema: DBSchemaModel = DBSchemaModel.from_str(target_db_schema_str)  # type: ignore
        db_schema_config: DBConfigModel = DBConfigModel.from_str(db_schema_config_str)  # type: ignore
        adapted_db_schema = db_schema_config.adapt_schema(db_schema, db_semantics)
        target_tables_schemas: dict[DataSourceId, TargetTableSchemaExt] = adapted_db_schema.parse_with_db_semantics(
            db_semantics
        )
        parser = ProposedPathsGenerator(adaptor, {}, target_tables_schemas)

        return parser.get_proposed_paths(source_table_name, source_field_name, target_table_name, target_field_name)
