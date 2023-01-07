import abc
from typing import Iterator, Mapping, Iterable, Any, Tuple

from etymmap.utils import tFlexStr


class Query(abc.ABC):
    __slots__ = ()


class EntryQueryBuilder(abc.ABC):
    @abc.abstractmethod
    def namespaces(self, *ns: int) -> "EntryQueryBuilder":
        pass

    @abc.abstractmethod
    def title(self, title: tFlexStr = None) -> "EntryQueryBuilder":
        pass

    @abc.abstractmethod
    def sections(self, *sections: tFlexStr) -> "EntryQueryBuilder":
        pass

    @abc.abstractmethod
    def language(self, *languages: str) -> "EntryQueryBuilder":
        pass

    @abc.abstractmethod
    def filter(self, filter: Any = None) -> "EntryQueryBuilder":
        pass

    @abc.abstractmethod
    def selector(self, selector: Any = None) -> "EntryQueryBuilder":
        pass

    @abc.abstractmethod
    def build(self) -> Query:
        pass


class EntryStore(abc.ABC):
    @classmethod
    @abc.abstractmethod
    def from_config(cls, config: Mapping) -> "EntryStore":
        pass

    @classmethod
    @abc.abstractmethod
    def builder(cls) -> EntryQueryBuilder:
        pass

    @abc.abstractmethod
    def __contains__(self, key: Tuple[str, ...]) -> bool:
        pass

    @abc.abstractmethod
    def __len__(self) -> int:
        pass

    @abc.abstractmethod
    def __iter__(self) -> Iterator[Mapping]:
        """
        Iterate over the entries
        """

    @abc.abstractmethod
    def add(self, entries: Iterable[Mapping], ordered=False) -> None:
        """
        Insert entries
        """

    @abc.abstractmethod
    def find(self, query: Query) -> Iterable[Mapping]:
        """
        Iterate over all entries matching the query
        """

    @abc.abstractmethod
    def remove(self, query: Query) -> None:
        """
        Remove the entry/entries that match the query
        """

    @abc.abstractmethod
    def clear(self) -> None:
        """
        Clear all entries
        """
