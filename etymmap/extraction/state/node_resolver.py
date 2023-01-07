import abc
from typing import List, Mapping, Optional

import wikitextparser as wtp

from etymmap.graph import LexemeBase, Node
from etymmap.wiktionary import Wiktionary
from .gloss_matching import GlossMatcherABC, GlossMergeListener


class NodeResolverABC(abc.ABC):
    @classmethod
    @abc.abstractmethod
    def from_wiktionary(
        cls,
        wiktionary: Wiktionary,
        gloss_matcher: GlossMatcherABC = None,
        merge_listener: GlossMergeListener = None,
    ):
        pass

    class NotContained(BaseException):
        pass

    class Underspecified(BaseException):
        pass

    @abc.abstractmethod
    def resolve_section(
        self,
        section: List[str],
        lexemes: List[LexemeBase],
        entry: Mapping = None,
    ) -> Optional[LexemeBase]:
        """
        :param section: a section within the article
        :param lexemes: the list of candidate lexemes
        :param entry: the original entry
        :return: the lexeme whose scope contains the section
        :raises: NotContained if section could not be associated with a lexeme
        """
        pass

    @abc.abstractmethod
    def resolve_template(
        self, template_data: Mapping, ctx_lexeme: LexemeBase
    ) -> Optional[Node]:
        """
        :param template_data: template data extracted by the template handler
        :param ctx_lexeme: the Lexeme whose sections contain the template
        :return: the linked node
        :raises: Underspecified if there are mulitple candidates
        """

    @abc.abstractmethod
    def resolve_link(
        self, wikilink: wtp.WikiLink, ctx_lexeme: LexemeBase
    ) -> Optional[Node]:
        """
        :param wikilink: a wikilink
        :param ctx_lexeme: the Lexeme whose sections contain the link
        :return: the linked node
        :raises: Underspecified if there are multiple candidatess
        """
