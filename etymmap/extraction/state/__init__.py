from typing import Type

import pandas as pd

from etymmap.wiktionary import Wiktionary
from .entities import Entities
from .gloss_matching import (
    GlossMatcherABC,
    GlossMergeListener,
    AllFeaturesGlossMatcher,
    NoFuzzyGlossMatcher,
    LogisticRegressionGlossMatcher,
    Levenshtein,
)
from .lexicon import LexiconABC
from .node_resolver import NodeResolverABC


class State:
    __slots__ = ("wiktionary", "lexicon", "entities", "node_resolver")
    wiktionary: Wiktionary
    lexicon: LexiconABC
    entities: Entities
    node_resolver: NodeResolverABC

    @classmethod
    def configure(
        cls,
        wiktionary: Wiktionary,
        lexicon: LexiconABC,
        entities: Entities,
        node_resolver: NodeResolverABC,
    ):
        cls.wiktionary = wiktionary
        cls.lexicon = lexicon
        cls.entities = entities
        cls.node_resolver = node_resolver

    @classmethod
    def init_and_configure(
        cls,
        wiktionary: Wiktionary,
        lexicon: Type[LexiconABC],
        node_resolver: Type[NodeResolverABC],
        entities: Entities = Entities(),
        wiktionary_index: pd.DataFrame = None,
        gloss_matcher: GlossMatcherABC = None,
        merge_listener: GlossMergeListener = None,
    ):
        lexicon_inst = lexicon.from_wiktionary(wiktionary, wiktionary_index)
        node_resolver_inst = node_resolver.from_wiktionary(
            wiktionary, gloss_matcher, merge_listener
        )
        cls.configure(wiktionary, lexicon_inst, entities, node_resolver_inst)
