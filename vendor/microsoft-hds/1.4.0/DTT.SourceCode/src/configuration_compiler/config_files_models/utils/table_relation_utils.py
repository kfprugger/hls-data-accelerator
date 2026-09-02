from dmf.model.target_configuration.target_table_schema import ForeignKey, TableRelation


def copy_with_fks(self: TableRelation, fks: list[ForeignKey]) -> TableRelation:
    return TableRelation(
        foreign_keys=tuple(fks), from_entity=self.from_entity, to_entity=self.to_entity
    )
