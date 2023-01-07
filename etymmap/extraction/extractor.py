import logging
import re

from tqdm import tqdm

from etymmap.extraction.state import State
from etymmap.graph import (
    ReducedRelations,
)
from etymmap.utils import FlexDict
from .section_extractor import SectionExtractor


class EtymologyExtractor:
    def __init__(
        self,
        *section_extractors: SectionExtractor,
        relation_store: ReducedRelations = ReducedRelations(),
    ):
        """
        Extracts an etymology graph from the wiktionary

        section_extractors: extractors for different sections
        """
        self.section_extractors = FlexDict(
            {extractor.sections: extractor for extractor in section_extractors}
        )
        self.relation_store = relation_store
        self.logger = logging.getLogger("Extractor")

    def collect_relations(self, progress=False, head=0):
        """
        Identifies etymological relations by applying the parsers to the sections
        """
        self.logger.info("Collect relations")
        # match all sections at once, for db-query
        all_sections = re.compile(
            "|".join(
                [
                    re.escape(s) if isinstance(s, str) else s.pattern
                    for s in self.section_extractors
                ]
            ),
            re.IGNORECASE,
        )
        section_iter = enumerate(State.wiktionary.sections(all_sections))
        if progress:
            section_iter = tqdm(section_iter, unit=" sections")
        for i, (section, section_text, ctx_entry) in section_iter:
            if head and i >= head:
                break
            extractor = self.section_extractors.get(section[-1])

            # this can happen if the all_sections regex matches too much
            if not extractor:
                continue

            term, language = ctx_entry["title"], ctx_entry["language"]
            lexemes = State.lexicon.get(term, language)
            if not lexemes:
                self.logger.info(f"No lexemes for {term}, {language}")

            ctx_lexeme = State.node_resolver.resolve_section(
                section, lexemes, entry=ctx_entry
            )

            # the context lexeme was not identified as a node (most cases: Letter entries)
            if not ctx_lexeme:
                continue

            # delegate to the right section extractor
            for relation in extractor.extract(section, ctx_lexeme, section_text):
                self.relation_store.add(relation)

    def get_graph(self, transitive_reduce, reduce_unspecific):
        return self.relation_store.finalize(
            transitive_reduce=transitive_reduce, reduce_unspecific=reduce_unspecific
        )
