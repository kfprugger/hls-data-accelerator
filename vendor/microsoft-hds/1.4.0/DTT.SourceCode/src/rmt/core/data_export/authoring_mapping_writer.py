from abc import abstractmethod
from typing import List

from rmt.core.data_management.authoring_mapping_entry import AuthoringMappingEntry


class AuthoringMappingWriter:

    @abstractmethod
    def write(self, authoring_mapping_entries: List[AuthoringMappingEntry]):
        pass
