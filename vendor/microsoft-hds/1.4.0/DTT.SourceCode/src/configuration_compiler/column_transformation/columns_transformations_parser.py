from collections import defaultdict
from typing import List, Optional, Set

from configuration_compiler.column_transformation.data_transformation_generator import DataTransformationGenerator
from configuration_compiler.column_transformation.empty_transformations_cleaner import EmptyTransformationsCleaner
from configuration_compiler.column_transformation.fk_transformations_generator import (
    ForeignKeysTransformationsGenerator,
)
from configuration_compiler.column_transformation.ids_mapping_helper import IdsMappingHelper
from configuration_compiler.column_transformation.missings_pks_filler import MissingPKsFiller
from configuration_compiler.column_transformation.relationships_generator import Relationship, RelationshipsGenerator
from configuration_compiler.column_transformation.tables_path_resolver import TableNamesPair, TablesPathResolver
from configuration_compiler.config_files_models.adapter.ext_model import AdapterModel
from configuration_compiler.config_files_models.adapter.model import SourceField, SourceTable, TargetField
from configuration_compiler.schema_graph import SchemaGraph
from configuration_compiler.spec_models.target_table_schema import TargetTableSchemaExt
from common.model.types import DataSourceId, TargetId
from dmf.model.target_configuration.target_transformation import ColumnTransformation


class ColumnsTransformationsParser:
    """
    This class is responsible for parsing the transformations between the source and target columns.
    It uses the following classes:
    - TablesPairGenerator: generates all the possible pairs of tables that can be used to generate the transformations
    - TablesPathResolver: resolves the path between two tables
    - DataTransformationGenerator: generates the transformations between two tables
    - ForeignKeysTransformationGenerator: generates the transformations between two tables based on the foreign keys
    - MissingPKsFiller: generates the transformations between two tables based on the missing primary keys
    - EmptyTransformationsCleaner: cleans the empty transformations

    High level flow:
    1. for each adapter source table:
        a. Generate all the possible pairs of tables, and the relation between them.
            for each relation- compute the required transformation of foreign key
        b. Generate the explicit transformations as listed in the adapter (data and primary keys)
        c. Remove the `empty` transformations- empty transformations are transformations for tables
            that only transform the PKs and for that table there are no data columns transformations.
    """

    def __init__(
        self,
        dmf_adaptor: AdapterModel,
        target_tables_schemas: dict[DataSourceId, TargetTableSchemaExt],
    ):
        self.transformations: dict[DataSourceId, dict[TargetId, Set[ColumnTransformation]]] = defaultdict(
            lambda: defaultdict(set)
        )
        self.dmf_adaptor = dmf_adaptor
        self.schema_graph = SchemaGraph(target_tables_schemas)
        self.target_tables_schemas = target_tables_schemas
        self.ids_mapping_helper = IdsMappingHelper(self.target_tables_schemas)

    def parse_column_transformations(self):
        """
        Parses the column transformations for each transformation defined in the adapter.

        This function iterates over each source table in the adapter, computes the relationships for all of the source table related mappings,
        generates the required transformations for the source table, fills in any unmapped primary keys, and cleans
        transformations without data. The parsed transformations are stored in the `transformations` attribute of the class.

        Returns:
            dict: A dictionary where the keys are the source table names and the values are dictionaries.
                  Each inner dictionary has target table IDs as keys and sets of ColumnTransformation objects as values.
        """
        for source_table in self.dmf_adaptor.source_tables:
            relationships = self._compute_relationships_for_source_table(source_table)
            self._generate_required_transformations_for_source_table(relationships, source_table)
            self._fill_in_unmapped_primary_keys(source_table.tableName)
            self._clean_transformations_without_data(source_table.tableName)
        return self.transformations

    def _clean_bidirectional_relationships_with_anchor(self,
                                                       relationships: Set[Relationship],
                                                       anchors: List[str]) -> Set[Relationship]:

        def _is_bidirectional_relationship_with_anchor(relationship_to_anchor: Relationship, other_relationship: Relationship) -> bool:
            return other_relationship.origin.id == relationship_to_anchor.destination.id and other_relationship.destination.id == relationship_to_anchor.origin.id

        relationships_to_anchors: Set[Relationship] = set()
        result: Set[Relationship] = set()

        for relationship in relationships:
            if relationship.destination.id in anchors:
                relationships_to_anchors.add(relationship)
            else:
                result.add(relationship)

        for relationship_to_anchor in relationships_to_anchors:
            is_bidirectional = False
            for any_other in result:
                is_bidirectional = is_bidirectional or _is_bidirectional_relationship_with_anchor(relationship_to_anchor, any_other)
            if not is_bidirectional:
                result.add(relationship_to_anchor)

        return result

    def _compute_relationships_for_source_table(self, source_table: SourceTable):
        """
        Computes all the relationships between each target and all anchor tables for a given source table.

        This function iterates over each source field in the given source table, and for each source field,
        it iterates over each target field. For each target field, it computes the table names pairs and
        then computes the relationships for these pairs.

        Args:
            source_table (SourceTable): The source table for which to compute the relationships.

        Returns:
            Set[Relationship]: A set of Relationship objects representing the relationships between each target
                               and all anchor tables for the given source table.
        """
        anchors = [anc.tableName for anc in source_table.targetAnchorTables]
        relationships: Set[Relationship] = set()
        for source_field in self.dmf_adaptor.source_fields_on_source_table(source_table):
            for target_field in self.dmf_adaptor.target_fields_on_source_field(source_field):
                table_names_pairs = self._compute_tables_names_pairs(anchors, source_table, target_field)
                relationships |= self._compute_relationships(table_names_pairs)
        relationships = self._clean_bidirectional_relationships_with_anchor(relationships, anchors)
        return relationships

    def _generate_required_transformations_for_source_table(
        self, relationships: Set[Relationship], source_table: SourceTable
    ):
        data_transformations = self._generate_data_transformations(source_table)
        fk_transformations = self._generate_fk_transformations(relationships, source_table, data_transformations)
        self._update_transformations(fk_transformations | data_transformations, source_table)

    def _generate_fk_transformations(
        self,
        relationships: Set[Relationship],
        source_table: SourceTable,
        data_transformations: Set[ColumnTransformation],
    ):
        """
        Generates transformations based on the foreign keys. The foreign keys are computed from the relationships.
        If a foreign key transformation is already explicitly defined, it is skipped.

        Args:
            relationships (Set[Relationship]): A set of relationships for which to generate the transformations.
            source_table (SourceTable): The source table for which to generate the transformations.
            data_transformations (Set[ColumnTransformation]): A set of existing data transformations.

        Returns:
            Set[ColumnTransformation]: A set of ColumnTransformation objects representing the foreign key transformations
                                       for the given relationships and source table.
        """
        transformations = set()
        for relationship in relationships:
            if self._relationship_fk_is_already_explicitly_defined(relationship, data_transformations):
                continue
            transformations |= ForeignKeysTransformationsGenerator(
                self.dmf_adaptor, relationship, source_table, self.target_tables_schemas, self.ids_mapping_helper
            ).generate_fks_transformations()
        return transformations

    def _relationship_fk_is_already_explicitly_defined(
        self, realtionship: Relationship, data_transformations: Set[ColumnTransformation]
    ):
        for data_transformation in data_transformations:
            if data_transformation.transformation_target_id == realtionship.origin.id:
                for fk in realtionship.relation.foreign_keys:
                    if data_transformation.target_field_name == fk.from_attribute:
                        return True
        return False

    def _generate_data_transformations(self, source_table: SourceTable) -> Set[ColumnTransformation]:
        """
        Generates explicit transformations as listed in the adapter for the given source table.
        These transformations include both data and primary keys.

        Args:
            source_table (SourceTable): The source table for which to generate the transformations.

        Returns:
            Set[ColumnTransformation]: A set of ColumnTransformation objects representing the explicit transformations
                                       for the given source table.
        """
        transformations = set()
        for source_field in self.dmf_adaptor.source_fields_on_source_table(source_table):
            for target_field in self.dmf_adaptor.target_fields_on_source_field(source_field):
                if self._is_fk_transformation(target_field):
                    continue
                bypass_key_harmonization = bool(
                    source_table.bypassKeysHarmonization and not source_field.enforceKeyHarmonization
                )
                data_transformation = self._generate_explicit_transformations(
                    source_field, target_field, bypass_key_harmonization
                )
                if data_transformation:
                    transformations.add(data_transformation)
        return transformations

    def _is_fk_transformation(self, target_field: TargetField) -> bool:
        if target_field.targetField is not None and target_field.targetField != target_field.fieldName:
            return True
        return False

    def _compute_relationships(self, table_names_pairs: Set[TableNamesPair]) -> Set[Relationship]:
        return RelationshipsGenerator(self.target_tables_schemas).compute_relationships(table_names_pairs)

    def _update_transformations(self, all_transformations, source_table):
        """store created transformations
        some transformations are created more than once since paths between tables might overlap"""
        for transformation in all_transformations:
            source_transformations = self.transformations[source_table.tableName]
            target_transformations = source_transformations[transformation.transformation_target_id]
            target_transformations.add(transformation)

    def _generate_explicit_transformations(
        self, source_field: SourceField, target_field: TargetField, bypass_keys_harmonization: bool
    ) -> Optional[ColumnTransformation]:
        return DataTransformationGenerator(
            self.target_tables_schemas, self.ids_mapping_helper, bypass_keys_harmonization
        ).generate_data_transformation(source_field, target_field)

    def _compute_tables_names_pairs(
        self, anchors: List[str], source_table: SourceTable, target_field: TargetField
    ) -> Set[TableNamesPair]:
        path_resolver = TablesPathResolver(
            anchors,
            self.schema_graph,
            self.target_tables_schemas,
            self.dmf_adaptor.target_table_paths,
            source_table.tableName,
            target_field,
        )
        return path_resolver.generate_pairs()

    def _clean_transformations_without_data(self, source_table_name: str):
        """if we have fk transformations which refer tables without data transformations, we remove them.
        This is because we don't want to generate fk values for tables without data.
        for that matter, ref tables are not considered as tables with data always
        """
        transformations_from_source_table = self.transformations[source_table_name]
        EmptyTransformationsCleaner(self.target_tables_schemas).clean(transformations_from_source_table)

    def _fill_in_unmapped_primary_keys(self, source_table_name: str):
        transformations_from_source_table = self.transformations[source_table_name]
        MissingPKsFiller(self.target_tables_schemas, transformations_from_source_table).fill_in_unmapped_primary_keys()
