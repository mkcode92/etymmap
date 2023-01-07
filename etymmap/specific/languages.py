import abc
from typing import Mapping, List, Union, Set


class LanguageDataUpdaterABC(abc.ABC):
    @abc.abstractmethod
    def make_language_data(self) -> Mapping[str, Mapping]:
        """
        Provides the base data for the LanguageMapper

        :return: a mapping from identifiers to language information that can be used by the LanguageMapper
        """

    @abc.abstractmethod
    def make_family_data(self) -> Mapping[str, Mapping]:
        """
        Provides a Mapping of language family codes
        """


class LanguageMapperABC(abc.ABC):
    UNKNOWN_LANGUAGE = "?"

    @abc.abstractmethod
    def __contains__(self, code: str):
        pass

    @property
    @abc.abstractmethod
    def codes(self) -> Set[str]:
        pass

    @property
    @abc.abstractmethod
    def names(self) -> Set[str]:
        pass

    @property
    @abc.abstractmethod
    def canonical_names(self) -> Set[str]:
        pass

    @abc.abstractmethod
    def code2name(self, code: str) -> str:
        """
        Maps a wiki language code or language family code to it's canonical name

        :raise KeyError if code is unknown
        """

    @abc.abstractmethod
    def name2code(
        self,
        name: str,
        prefer_detailed=True,
        prefer_language=True,
        allow_ambiguity=False,
    ) -> Union[str, List[str]]:
        """
        Maps a name (canonical or other) to the code used in wiktionary

        :param name: a language name
        :param prefer_detailed: for ambiguous name, try to resolve to the code that has more information
        :param prefer_language: if a name refers both to a language and a family, then return the language
        :param allow_ambiguity: allow multiple codes as result, else use self.resolve_ambiguity to disambiguate
        :return the single name or a list of names, if ambiguity is allowed
        :raise KeyError
        """

    @abc.abstractmethod
    def code2parent(self, code: str, *args, **kwargs):
        """
        :param code: a wiktionary language code
        :param args:
        :param kwargs:
        :return:
        """

    @abc.abstractmethod
    def is_family(self, code: str) -> bool:
        """
        True if code refers to a language family instead of a language
        """

    @abc.abstractmethod
    def get_family(self, code: str) -> str:
        """
        Get the code of the language family
        """

    @abc.abstractmethod
    def normalize(self, term: str, code: str = None) -> str:
        pass

    def resolve_ambiguity(self, cands: List[str]) -> str:
        return cands[0]
