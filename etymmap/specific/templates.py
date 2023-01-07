import abc
import json
from typing import Dict, Union, Tuple, Mapping, Set, List, Optional

import wikitextparser as wtp

from etymmap.graph.relation_types import RelationType
from etymmap.utils import tFlexStr

TemplateParameter = Tuple[Union[str, Tuple[str, int]], str]


class LinkNormalization:
    NO_TARGET = object()  # explicit not set

    __slots__ = ("relation", "link_source", "link_target")

    def __init__(
        self,
        relation: Dict,
        link_source: Union[Dict, Tuple[Dict, ...]] = None,
        link_target: Union[Dict, Tuple[Dict, ...]] = None,
    ):
        self.relation = relation
        self.link_source = link_source
        self.link_target = link_target

    def __repr__(self):
        return json.dumps(
            {
                "relation": {
                    k: v if k != "type" else v.name for k, v in self.relation.items()
                },
                "link_source": self.link_source
                if self.link_source is not self.NO_TARGET
                else "NO_TARGET",
                "link_target": self.link_target
                if self.link_target is not self.NO_TARGET
                else "NO_TARGET",
            },
            indent=2,
        )


class LinkSemantics(abc.ABC):
    @abc.abstractmethod
    def __call__(
        self, default_relation: RelationType, template_args: List[TemplateParameter]
    ) -> LinkNormalization:
        """
        Converts the decomposed template into a tuple of relation, source(s), target(s), representation
        """


class TemplateHandler(abc.ABC):
    """
    Interface to access template information
    """

    @abc.abstractmethod
    def to_normalization(
        self, template: wtp.Template, recursive: bool = True
    ) -> LinkNormalization:
        """
        Transform a template into a link normalization

        :param template: a template or template representation
        :param recursive: hint for plain text mapper: True if contains other wikitext elements
        :return: a LinkNormalization
        """

    @abc.abstractmethod
    def to_text(self, template: wtp.Template, recursive: bool = True) -> str:
        """
        Transform a template to plain text

        :param template: a template or template representation
        :param recursive: hint for plain text mapper: True if contains other wikitext elements
        :return: the template as plain text
        """

    @abc.abstractmethod
    def templates_to_relation(self, alias=True) -> Mapping[str, RelationType]:
        """
        :param alias: also consider alias template names
        :return: a map from template names to the default relation type
        """

    @abc.abstractmethod
    def get_names(self) -> Mapping[str, Set[tFlexStr]]:
        """
        :return: a mapping from representatives to alias/ equivalent names
        """

    @abc.abstractmethod
    def get_relation_mapping(self) -> Mapping[RelationType, Set[str]]:
        """
        :return: a mapping of default relation types to representatives
        """

    def determine_pos(
        self, template_pos: str = None, gloss: str = None
    ) -> Optional[str]:
        """
        given the template parameters pos and gloss, find a somehow canonical gloss
        """
        return template_pos
