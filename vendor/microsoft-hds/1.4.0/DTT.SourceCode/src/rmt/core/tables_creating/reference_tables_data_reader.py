from abc import ABC, abstractmethod

from rmt.core.tables_creating.model.internal import ReferenceTableData


class ReferenceTablesDataReader(ABC):
    @abstractmethod
    def read(self) -> dict[str, list[ReferenceTableData]]:
        pass
