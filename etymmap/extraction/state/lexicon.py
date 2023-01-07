import abc
from pathlib import Path
from typing import Iterable, Mapping, List, Union

import pandas as pd

from etymmap.graph import LexemeBase
from etymmap.wiktionary import Wiktionary


class LexiconABC(abc.ABC):
    @classmethod
    @abc.abstractmethod
    def from_wiktionary(cls, wiktionary: Wiktionary, index: pd.DataFrame = None):
        pass

    @classmethod
    @abc.abstractmethod
    def read_pickle(cls, path: Union[str, Path]):
        pass

    @abc.abstractmethod
    def to_pickle(self, path: Union[str, Path]):
        pass

    @abc.abstractmethod
    def add_from_entry(self, entry: Mapping) -> List[LexemeBase]:
        """
        :param entry: a wiktionary entry
        :return: the lexemes that are represented by the entry
        """

    @abc.abstractmethod
    def add_no_entry(
        self, term: str, language: str, template_data: Mapping = None
    ) -> LexemeBase:
        pass

    @abc.abstractmethod
    def get(
        self, term: str, language: str = None, sense_idx: int = 0
    ) -> List[LexemeBase]:
        pass

    @abc.abstractmethod
    def __iter__(self) -> Iterable[LexemeBase]:
        pass
