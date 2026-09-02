class AuthoringMappingEntry:
    def __init__(self, contributor_name: str, table_name: str, target_key: int, source_value: str):
        self.contributor_name = contributor_name
        self.table_name = table_name
        self.target_key = target_key
        self.source_value = source_value

    def __eq__(self, other: object) -> bool:
        if isinstance(other, AuthoringMappingEntry):
            return (
                self.contributor_name == other.contributor_name
                and self.table_name == other.table_name
                and self.target_key == other.target_key
                and self.source_value == other.source_value
            )
        else:
            raise ValueError(f"Invalid comparison between AuthoringMappingEntry and {type(other)}")
