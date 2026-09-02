from collections import defaultdict
from dataclasses import dataclass
from typing import List, Set

from configuration_compiler.column_transformation.ids_mapping_helper import IdsMappingHelper
from configuration_compiler.column_transformation.relationships_generator import Relationship, RelationshipsGenerator
from configuration_compiler.column_transformation.tables_path_resolver import TablesPathResolver
from configuration_compiler.config_files_models.adapter.ext_model import AdapterModel
from configuration_compiler.schema_graph import SchemaGraph
from configuration_compiler.spec_models.target_table_schema import TargetTableSchemaExt
from common.model.types import DataSourceId, TargetId
from dmf.model.target_configuration.target_transformation import ColumnTransformation


class TransformationNotFoundException(Exception):
    pass


@dataclass
class ProposedPathsResponse:
    """
    The ProposedPathsResponse class is responsible for holding the response of the proposed paths generator.
    tables and links are lists of lists because each path is a list of tables and each link is a list of relationships.
    They have corresponding indices in the lists.
    """
    source_table_name: str
    source_field_name: str
    tables: List[List[TargetTableSchemaExt]]
    links: List[List[Relationship]]
    paths_scores: List[int]
    target_field_name: str


class ProposedPathsGenerator:
    """
    The ProposedPathsGenerator class is responsible for generating proposed paths between a pair of source table and a target table.

    Methods
    -------
    get_proposed_paths(source_table_name, source_field_name, target_table_name, target_field_name):
        Uses TablesPathResolver to generate proposed paths between the given source table and target table.
        Returns a ProposedPathsResponse object containing the proposed paths from the source table to the target field.

    _generate_proposed_paths_response(source_table_name, source_field_name, target_field_name, path_resolver):
        Generates a ProposedPathsResponse object for the given source table, source field, target field, and path resolver.

    Attributes
    ----------
    transformations : dict
        A dictionary mapping from DataSourceId to a dictionary mapping from TargetId to a set of ColumnTransformations.
    dmf_adaptor : AdapterModel
        The DMF adapter used to retrieve source tables and fields.
    tables_paths_overrides : dict
        A dictionary mapping from DataSourceId to a dictionary mapping from TargetId to a list of TargetIds.
    schema_graph : SchemaGraph
        The schema graph used to resolve table paths.
    target_tables_schemas : dict
        A dictionary mapping from DataSourceId to TargetTableSchemaExt. This is the target ERD description.

    ids_mapping_helper : IdsMappingHelper
        The helper used to decide if atransformation should be mapped. This is only here for compatibility with the old code.
        might be removed in the future only for this API by making it optional.
    """

    def __init__(
        self,
        dmf_adaptor: AdapterModel,
        tables_paths_overrides: dict[DataSourceId, dict[TargetId, List[TargetId]]],
        target_tables_schemas: dict[DataSourceId, TargetTableSchemaExt],
    ):
        self.transformations: dict[DataSourceId, dict[TargetId, Set[ColumnTransformation]]] = defaultdict(
            lambda: defaultdict(set)
        )
        self.dmf_adaptor = dmf_adaptor
        self.tables_paths_overrides = tables_paths_overrides
        self.schema_graph = SchemaGraph(target_tables_schemas)
        self.target_tables_schemas = target_tables_schemas
        self.ids_mapping_helper = IdsMappingHelper(self.target_tables_schemas)

    def get_proposed_paths(
        self, source_table_name: str, source_field_name: str, target_table_name: str, target_field_name: str
    ) -> ProposedPathsResponse:
        for source_table in self.dmf_adaptor.source_tables:
            if source_table.tableName == source_table_name:
                anchors = [anc.tableName for anc in source_table.targetAnchorTables]
                for source_field in self.dmf_adaptor.source_fields_on_source_table(source_table):
                    if source_field.fieldName == source_field_name:
                        for target_field in self.dmf_adaptor.target_fields_on_source_field(source_field):
                            if (
                                target_field.tableName == target_table_name
                                and target_field.fieldName == target_field_name
                            ):
                                path_resolver = TablesPathResolver(
                                    anchors,
                                    self.schema_graph,
                                    self.target_tables_schemas,
                                    self.tables_paths_overrides,
                                    source_table.tableName,
                                    target_field,
                                )
                                return self._generate_proposed_paths_response(
                                    source_table_name, source_field_name, target_field_name, path_resolver
                                )
        raise TransformationNotFoundException("Cannot find source table or target field")

    def _generate_proposed_paths_response(
        self, source_table_name: str, source_field_name: str, target_field_name: str, path_resolver: TablesPathResolver
    ) -> ProposedPathsResponse:
        proposed_paths = path_resolver.get_proposed_paths()
        scores = [path_resolver.path_score(path) for path in proposed_paths]
        proposed_paths_with_context = []
        links = []
        for path in proposed_paths:
            proposed_paths_with_context.append([self.target_tables_schemas[target_id] for target_id in path])
            table_names_pairs = path_resolver.tables_path_to_tables_pairs(path)
            relationships = RelationshipsGenerator(self.target_tables_schemas).compute_relationships(table_names_pairs)
            links.append(list(relationships))
        return ProposedPathsResponse(
            source_table_name=source_table_name,
            source_field_name=source_field_name,
            tables=proposed_paths_with_context,
            links=links,
            paths_scores=scores,
            target_field_name=target_field_name,
        )
