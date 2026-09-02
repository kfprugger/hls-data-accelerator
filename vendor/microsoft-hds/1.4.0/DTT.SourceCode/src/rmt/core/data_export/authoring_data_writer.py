from abc import abstractmethod
from typing import List

from rmt.core.data_management.authoring_data_entry import AuthoringDataEntry


class AuthoringDataWriter:

    @abstractmethod
    def write(self, authoring_data_entries: List[AuthoringDataEntry]):
        pass
