import logging
from typing import List, Mapping, Optional

import wikitextparser as wtp

from etymmap.graph import (
    LexemeBase,
    NoEntryLexeme,
    Node,
    SingleMeaningStub,
    EntryLexeme,
    Gloss,
)
from etymmap.specific import Specific
from etymmap.utils import analyze_link_target
from etymmap.wiktionary import Wiktionary
from ..state import NodeResolverABC, GlossMatcherABC, GlossMergeListener, State


class NodeResolver(NodeResolverABC):
    def __init__(
        self,
        wiktionary: Wiktionary,
        gloss_matcher: GlossMatcherABC = None,
        merge_listener: GlossMergeListener = None,
    ):
        self.wiktionary = wiktionary
        self.gloss_matcher = gloss_matcher
        self.merge_listener = merge_listener or GlossMergeListener()
        self.logger = logging.getLogger("NodeResolver")

    @classmethod
    def from_wiktionary(
        cls,
        wiktionary: Wiktionary,
        gloss_matcher: GlossMatcherABC = None,
        merge_listener: GlossMergeListener = None,
    ):
        return cls(wiktionary, gloss_matcher, merge_listener)

    def resolve_section(
        self,
        section: List[str],
        lexemes: List[LexemeBase],
        entry: Mapping = None,
    ) -> Optional[LexemeBase]:

        if len(lexemes) == 1:
            return lexemes[0]

        # ideally, the section is in the scope of a etymology section
        sense_idx = 0
        try:
            sense_idx = Specific.entry_parser.get_sense_index(section)
        except ValueError:
            if not entry:
                # check pos section
                cands = [
                    lexeme
                    for lexeme in lexemes
                    if (any(gloss.pos == section[-1]) for gloss in lexeme.glosses)
                ]
                if len(cands) == 1:
                    return cands[0]

                # now we have to check the entry
                key = lexemes[0].term, lexemes[0].language
                self.logger.debug(
                    f"Get entry to identify section/ anchor {lexemes[0]}/{section}"
                )
                entry = self.wiktionary[key][0]

            full_sections = [
                (i, s)
                for i, s in enumerate(entry["sections"])
                if s[-len(section) :] == section
            ]
            if len(full_sections) == 1:
                idx, full_section = full_sections[0]
                get_sense_index = Specific.entry_parser.get_sense_index
                try:
                    sense_idx = get_sense_index(full_section)
                except ValueError:
                    # try previous section
                    for previous_section in entry["sections"][idx:0:-1]:
                        try:
                            sense_idx = get_sense_index(previous_section)
                            break
                        except ValueError:
                            continue
                    else:
                        self.logger.warning(
                            f"Section outside Etymology scope: {section} in ({entry['title']},{entry['language']})"
                        )
                        return
        try:
            ret = lexemes[sense_idx]
            if sense_idx == ret.sense_idx:
                return ret
        except IndexError:
            pass
        for lexeme in lexemes:
            if lexeme.sense_idx == sense_idx:
                return lexeme
        # we only warn if lexeme is not a single letter
        if len(lexemes[0].term) > 1:
            self.logger.warning(f"Could not find {section} ({sense_idx}) in {lexemes}")

    def resolve_template(
        self, template_data: Mapping, ctx_lexeme: LexemeBase = None
    ) -> Optional[Node]:
        name = template_data.get("name")
        if name:
            return State.entities.identify(name, template_data)

        term, language = (template_data.get(k) for k in ("term", "language"))
        if ctx_lexeme:
            term = term or ctx_lexeme.term
            language = language or ctx_lexeme.language

        # the lexicon only cares about entry languages
        if language:
            if (
                not Specific.language_mapper.is_family(language)
                and language in Specific.language_mapper
            ):
                language = Specific.language_mapper.code2parent(language) or language
        elif ctx_lexeme:
            language = ctx_lexeme.language

        if term == "-":
            # indicates that the term should not be linked
            return

        term, section, category = analyze_link_target(term)
        if category == "wikipedia":
            return State.entities.identify(term)
        elif category and category != "Reconstruction":
            self.logger.debug(f"Unexpected link in template {template_data}")
            return
        term = Specific.language_mapper.normalize(term, language)
        return self._identify_lexeme(
            term or ctx_lexeme.term,  # defaults to current entry name
            language or ctx_lexeme.language,  # defaults to current entry languages
            template_data=template_data,
            anchor=section,
        )

    def resolve_link(
        self, wikilink: wtp.WikiLink, ctx_lexeme: LexemeBase = None
    ) -> Optional[Node]:
        term, anchor, category = analyze_link_target(wikilink.target)
        if category:
            if category == "wikipedia":
                return State.entities.identify(term)
            elif category != "Reconstruction":
                # ignore files, images, category links, etc.
                return
        language = None
        if anchor:
            try:
                language = Specific.language_mapper.name2code(anchor)
                anchor = None
            except KeyError:
                pass
        return self._identify_lexeme(
            term or ctx_lexeme.term,
            language or ctx_lexeme.language,
            template_data=None,
            anchor=anchor,
        )

    def _identify_lexeme(
        self,
        term: str,
        language: str,
        template_data: Mapping = None,
        anchor: str = None,
    ) -> Optional[Node]:
        """
        Identify the lexeme that is referred to by a template or link

        :return: the best lexeme, according to information in obj
        """
        _e = self.merge_listener.Event
        homonyms = State.lexicon.get(term=term, language=language)

        # a new lexeme that is not yet in the lexicon
        if not homonyms:
            return State.lexicon.add_no_entry(term, language, template_data)

        if len(homonyms) == 1:
            cand = homonyms[0]
            if isinstance(cand, SingleMeaningStub):
                return cand
            elif isinstance(cand, NoEntryLexeme):
                if template_data:
                    self._merge_no_entry_lexeme(cand, template_data)
                return cand

        if anchor:
            ret = self.resolve_section([anchor], homonyms)
            if ret:
                self.merge_listener(_e.Section, template_data, ret)
                return ret

        if not template_data:
            # there is no more information for a wikilink
            return self.fallback(homonyms)

        return self._identify_entry_lexeme(template_data, homonyms)

    def _identify_entry_lexeme(
        self, template_data: Mapping, homonyms: List[EntryLexeme]
    ):
        _e = self.merge_listener.Event

        id_ = template_data.get("id")  # map to sense_id
        if id_:
            try:
                return self._identify_by_senseid(
                    id_,
                    template_data,
                    homonyms,
                )
            except ValueError as ve:
                self.logger.warning(ve)

        # we do not factor this out for efficiency
        template_pos = template_data.get("pos")
        template_gloss = template_data.get("t", "")

        template_pos = Specific.template_handler.determine_pos(
            template_pos, template_gloss
        )

        cands = []
        if template_pos:
            cands = [
                (h, g.text)
                for h in homonyms
                for g in h.glosses
                if g.text and g.pos == template_pos
            ]
            if len(set(id(h) for h, _ in cands)) == 1:
                self.merge_listener(_e.Only1POS, template_data, cands[0][0])
                return cands[0][0]
        if not cands:
            cands = [(h, g.text) for h in homonyms for g in h.glosses if g.text]

        if cands and template_gloss:
            if self.merge_listener:
                for h, _ in cands:
                    self.merge_listener(_e.GlossMergeAttempt, template_data, h)
            try:
                return self.gloss_matcher.select(template_gloss, cands)
            except ValueError as ve:
                self.logger.warning(ve.args[0])

        qualifier = template_data.get("q")
        if qualifier:
            for cand in homonyms:
                for gloss in cand.glosses:
                    if gloss.labels and any(
                        label == qualifier for label in gloss.labels
                    ):
                        self.merge_listener(_e.LabelOrQual, template_data, cand)
                        return cand

        return self.fallback(homonyms)

    def fallback(self, candidates: List[Node], query=None):
        return candidates[0]

    def _identify_by_senseid(
        self, id_: str, template_data: Mapping, homonyms: List[EntryLexeme]
    ) -> Optional[EntryLexeme]:
        ids = []
        _e = self.merge_listener.Event
        for cand in homonyms:
            if cand.etymid == id_:
                self.merge_listener(_e.EtymIdMatch, template_data, cand)
                for other in homonyms:
                    if other is not cand:
                        self.merge_listener(_e.EtymIdOther, template_data, other)
                return cand
            for gloss in cand.glosses:
                gid = gloss.id
                if gid:
                    ids.append(gid)
                if gid == id_:
                    if self.merge_listener:
                        self.merge_listener(_e.SenseId, template_data, cand)
                        for other in homonyms:
                            if other is not cand:
                                self.merge_listener(_e.SenseId, template_data, other)
                    return cand

    def _merge_no_entry_lexeme(self, cand, template_data) -> None:
        pos = template_data.get("pos")
        gloss = template_data.get("gloss")
        if gloss or pos:
            if cand.glosses is None:
                cand.glosses = []
            cand.glosses.append(Gloss(pos=pos, text=gloss))
