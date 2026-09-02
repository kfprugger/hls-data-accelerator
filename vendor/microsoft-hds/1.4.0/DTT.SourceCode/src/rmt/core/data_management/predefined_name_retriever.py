from typing import List

from rmt.core.core_exceptions import NonExistingPredefinedNameError


class PredefinedNameRetriever:
    def __init__(self, name: str, predefined_names: List[str]):
        self.name = name
        self.name_lower = self.name.lower()
        self._predefined_names_lower_dict = {value.lower(): value for value in predefined_names}

    def is_name_not_in_predefined_names(self) -> bool:
        return self.name_lower not in self._predefined_names_lower_dict

    def get_name_in_same_casing_from_predefined_names(self) -> str:
        if self.is_name_not_in_predefined_names():
            raise NonExistingPredefinedNameError(self.name)
        return self._predefined_names_lower_dict[self.name_lower]
