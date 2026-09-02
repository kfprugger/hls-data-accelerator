from enum import Enum

from rmt.core.data_management.primitive_types import ContributorName


class ContributorType(Enum):
    Common = 1
    Industry = 2
    Customer = 3

    @staticmethod
    def from_name(name: str):
        if name.lower() == "common":
            return ContributorType.Common
        elif name.lower() == "customer":
            return ContributorType.Customer
        else:
            return ContributorType.Industry

    def __str__(self) -> str:
        return self.name


class KeysRange:
    """
    range of refernce table keys that a contributor in whcih contributor is alowed to add data to the table
    """

    @property
    def start(self) -> int:
        return self._start

    @property
    def end(self) -> int:
        return self._end

    def __init__(self, start: int, end: int):
        self._start = start
        self._end = end

    def __str__(self) -> ContributorName:
        return f"ContributorRange(start={self._start}, end={self._end})"


class Contributor:

    @property
    def name(self) -> ContributorName:
        return self._name

    @property
    def keys_range(self) -> KeysRange:
        return self._keys_range

    def __init__(self, name: ContributorName, keys_range: KeysRange):
        self._name = name
        self._keys_range = keys_range
        self._contributor_type = ContributorType.from_name(name)

    def is_key_in_contributor_keys_range(self, key: int) -> bool:
        return self._keys_range.start <= key <= self.keys_range.end

    def __hash__(self) -> int:
        return hash(self._name)

    def __eq__(self, __value) -> bool:
        if isinstance(__value, Contributor):
            return self._name == __value.name
        else:
            raise ValueError(f"Invalid comparison between Contributor and {type(__value)}")

    def __str__(self):
        return f"Contributor(name={self.name}, keys_range={self.keys_range})"
