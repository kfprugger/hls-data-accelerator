from common.model.base_source_configuration import BaseSourceTableSchema, BaseTableColumn
from configuration_compiler.config_files_models.common.entity_definition_container import EntityDefinitionContainer
import configuration_compiler.configuration_compiler_helpers as cc_helpers

from typing import Dict, List
from common.model.source_to_reference_mapping import SourceToReferenceMapping as CommonSourceToReferenceMapping
from common.model.data_access_definition import DataAccessDefinition as CommonDataAccessDefinition
from common.model.data_source_type_enum import DataSourceTypeEnum as CommonDataSourceTypeEnum
from configuration_compiler.config_files_models.env.ext_model import EnvConfigModel
from configuration_compiler.configuration_content_wrapper import RmtConfigurationContentWrapper
from configuration_compiler.config_files_models.adapter.ext_model import AdapterModel
from configuration_compiler.config_files_models.common.field_type import CommonParsing, FieldParsingExtraProps
from configuration_compiler.config_files_models.db_schema.ext_model import DBSchemaModel
from configuration_compiler.config_files_models.db_schema.model import ModelItem
from configuration_compiler.config_files_models.db_schema_config.ext_model import DBConfigModel
from configuration_compiler.config_files_models.semantics.ext_model import SemanticsModel
from configuration_compiler.config_files_models.semantics.model import ReferenceTable as SemanticReferenceTable
from configuration_compiler.rmt_reference_values_configuration import from_configuration
from configuration_compiler.source_tables_columns_config import parse_source_schema
from configuration_compiler.spec_models.target_table_schema import TargetTableSchemaExt
from common.model.data_access_definition import DataAccessDefinition
from common.model.data_source_type_enum import DataSourceTypeEnum
from common.model.types import DataSourceId
from dmf.model.reference_values_configuration import ReferenceValuesConfiguration
from common.model.source_to_reference_mapping import SourceToReferenceMapping
from dmf.model.source_configuration import SourceTableSchema as DmfSourceTableSchema
from rmt.contract.configuration import model as rmt_model
from rmt.contract.configuration.reference_table import TableColumn


class RMTConfigurationCompiler:
    @staticmethod
    def compile_rmt_model(config_content_wrapper: RmtConfigurationContentWrapper) -> rmt_model.Model:
        adaptor: AdapterModel = AdapterModel.from_str(config_content_wrapper.adaptor_file_content)
        db_semantics: SemanticsModel = SemanticsModel.from_str(config_content_wrapper.target_db_semantics_content)
        env_config: EnvConfigModel = EnvConfigModel.from_str(config_content_wrapper.env_config_content)
        db_schema: DBSchemaModel = DBSchemaModel.from_str(config_content_wrapper.target_db_schema_content)
        db_schema_config: DBConfigModel = DBConfigModel.from_str(config_content_wrapper.db_schema_config_content)
        adapted_db_schema = db_schema_config.adapt_schema(db_schema, db_semantics)

        target_tables_schemas: dict[DataSourceId, TargetTableSchemaExt] = adapted_db_schema.parse_with_db_semantics(
            db_semantics
        )

        source_entities_definition_container = EntityDefinitionContainer(
            name=cc_helpers.get_source_entities_container_name(adaptor, env_config),
            type=env_config.source_entities_container_type,
        )

        reference_values_configuration: ReferenceValuesConfiguration
        dmf_source_to_reference_mappings: Dict[DataSourceId, List[SourceToReferenceMapping]]
        dmf_source_to_reference_mappings = from_configuration(adaptor, target_tables_schemas)
        common_source_to_reference_mappings: Dict[str, List[CommonSourceToReferenceMapping]]
        common_source_to_reference_mappings = RMTConfigurationCompiler._convert_to_common(dmf_source_to_reference_mappings)

        dmf_source_schemas: dict[DataSourceId, DmfSourceTableSchema] = parse_source_schema(adaptor)
        source_configurations = set()
        for source_table in adaptor.source_tables:
            common_source_schema = dmf_source_schemas[source_table.tableName]
            data_access_definition = cc_helpers.generate_data_access_definition(
                env_config,
                source_entities_definition_container,
                source_table.tableName,
                query=source_table.query,
            )
            common_data_access_definition = RMTConfigurationCompiler._convert_data_access_definition_to_common(data_access_definition)
            source_configuration = cc_helpers.generate_source_config_for_rmt(
                source_id=source_table.tableName,
                source_to_reference_mappings=frozenset(
                    common_source_to_reference_mappings.get(source_table.tableName, [])
                ),
                data_access_definition=common_data_access_definition,
                table_schema=RMTConfigurationCompiler._dmf_source_schema_to_common_source_schema(common_source_schema),
            )
            source_configurations.add(source_configuration)

        return rmt_model.Model(
            source_domain=adaptor.sourceDomain,
            secondary_lake_location=env_config.secondary_lake_location,
            reference_tables=RMTConfigurationCompiler._gen_ref_tables_entries(
                db_semantics.referenceTables, adapted_db_schema
            ),
            source_configurations=frozenset(source_configurations)
        )

    @staticmethod
    def _dmf_source_schema_to_common_source_schema(dmf_source_schema: DmfSourceTableSchema) -> BaseSourceTableSchema:
        columns = []
        for dmf_column in dmf_source_schema.columns:
            common_column = BaseTableColumn(
                name=dmf_column.name,
                type=dmf_column.type,
                expression=dmf_column.expression
            )
            columns.append(common_column)

        return BaseSourceTableSchema(columns=frozenset(columns))

    @staticmethod
    def _convert_to_common(dmf_source_to_refernce_mappings: Dict[DataSourceId, List[SourceToReferenceMapping]]) -> Dict[str, List[CommonSourceToReferenceMapping]]:
        common_source_to_refernce_mappings: Dict[str, List[CommonSourceToReferenceMapping]] = dict()
        for source_id, dmf_source_to_refernce_mappings_list in dmf_source_to_refernce_mappings.items():
            common_source_to_refernce_mappings_list = []
            for dmf_source_to_refernce_mapping in dmf_source_to_refernce_mappings_list:
                common_source_to_refernce_mapping = CommonSourceToReferenceMapping(source_field_name=dmf_source_to_refernce_mapping.source_field_name,
                                                                                   target_reference_field_name=dmf_source_to_refernce_mapping.target_reference_field_name,
                                                                                   target_reference_table_name=dmf_source_to_refernce_mapping.target_reference_table_name)
                common_source_to_refernce_mappings_list.append(common_source_to_refernce_mapping)
            common_source_to_refernce_mappings[source_id] = common_source_to_refernce_mappings_list

        return common_source_to_refernce_mappings

    @staticmethod
    def _convert_data_access_definition_to_common(data_access_definition: DataAccessDefinition) -> CommonDataAccessDefinition:
        return CommonDataAccessDefinition(
            data_format=data_access_definition.data_format,
            data_source_id=data_access_definition.data_source_id,
            data_source_owner_id=data_access_definition.data_source_owner_id,
            data_source_type=RMTConfigurationCompiler._convert_data_source_type_to_common(data_access_definition.data_source_type)
        )

    @staticmethod
    def _convert_data_source_type_to_common(data_source_type: DataSourceTypeEnum) -> CommonDataSourceTypeEnum:
        match data_source_type.value:
            case data_source_type.QUERY:
                return CommonDataSourceTypeEnum.QUERY
            case data_source_type.TABLE:
                return CommonDataSourceTypeEnum.TABLE
            case data_source_type.STORAGE:
                return CommonDataSourceTypeEnum.STORAGE
            case _:
                raise ValueError(f"Unknown data source type '{data_source_type}'")

    @staticmethod
    def _gen_ref_tables_entries(
        ref_tables: list[SemanticReferenceTable], adapted_db_schema: DBSchemaModel
    ) -> list[rmt_model.ReferenceTable]:
        ref_tables_entries = []
        for ref_table in ref_tables:
            try:
                table_schema = adapted_db_schema.tables_dict[ref_table.table]
            except KeyError as ke:
                raise ValueError(f"Failed to find table {ref_table.table} in DB schema") from ke
            ref_tables_entries.append(
                rmt_model.ReferenceTable(
                    table_name=ref_table.table,
                    key_field=ref_table.keyField,
                    name_field=ref_table.nameField,
                    columns=RMTConfigurationCompiler._gen_ref_table_columns_entries_for_table(table_schema),
                )
            )
        return ref_tables_entries

    @staticmethod
    def _gen_ref_table_columns_entries_for_table(table_schema: ModelItem) -> list[TableColumn]:
        columns = []
        for column in table_schema.storageDescriptor.columns:
            columns.append(
                TableColumn(
                    name=column.name,
                    type=CommonParsing.parse_field_type(column.originDataTypeName.typeName,
                                                        FieldParsingExtraProps(precision=column.originDataTypeName.precision,
                                                                               scale=column.originDataTypeName.scale)),
                    is_nullable=column.originDataTypeName.isNullable,
                )
            )
        return columns
