import abc
from typing import Any, Mapping, List

from etymmap.graph import LexemeBase
from etymmap.utils import tMaybeParsed, SeqMap


class EntryParserABC(abc.ABC):
    NO_HEADING = "<no-heading>"

    @abc.abstractmethod
    def clean_title(self, title: str, namespace: int) -> str:
        pass

    @abc.abstractmethod
    def parse_section(self, text: tMaybeParsed) -> SeqMap:
        pass

    @abc.abstractmethod
    def make_gloss(self, text: tMaybeParsed, pos: str) -> Any:
        pass

    @abc.abstractmethod
    def make_pronunciation(self, text: tMaybeParsed) -> Any:
        pass

    @abc.abstractmethod
    def make_lexemes(self, entry: Mapping) -> List[LexemeBase]:
        pass

    @abc.abstractmethod
    def count_etymologies(self, sections: List[List[str]], texts: List[str]) -> int:
        pass

    @abc.abstractmethod
    def get_sense_index(self, section: List[str], match=None) -> int:
        pass
