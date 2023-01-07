import os
from typing import Type

import pandas as pd

from .defaults import Lexicon, NodeResolver
from .extractor import EtymologyExtractor
from .section_extractor import (
    SectionExtractor,
    BaselineExtractor,
    RelatedTermsExtractor,
    DerivedTermsExtractor,
    DescendantsSectionExtractor,
    EtymologySectionExtractor,
)
from .state import (
    LexiconABC,
    NodeResolverABC,
    Entities,
    GlossMatcherABC,
    GlossMergeListener,
    State,
)
from ..wiktionary import Wiktionary


def init_and_configure(
    wiktionary: Wiktionary,
    lexicon: Type[LexiconABC] = Lexicon,
    node_resolver: Type[NodeResolverABC] = NodeResolver,
    entities: Entities = Entities(),
    wiktionary_index: pd.DataFrame = None,
    gloss_matcher: GlossMatcherABC = None,
    merge_listener: GlossMergeListener = None,
    cache: str = None,
):
    if cache and os.path.isfile(cache):
        lexicon_inst = lexicon.read_pickle(cache)
    else:
        lexicon_inst = lexicon.from_wiktionary(wiktionary, wiktionary_index)
        if cache:
            lexicon_inst.to_pickle(cache)
    node_resolver_inst = node_resolver.from_wiktionary(
        wiktionary, gloss_matcher, merge_listener
    )
    State.configure(wiktionary, lexicon_inst, entities, node_resolver_inst)
