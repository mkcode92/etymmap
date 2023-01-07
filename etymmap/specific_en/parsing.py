import re
from typing import Any, Mapping, List

import wikitextparser as wtp

from etymmap.graph import Gloss, Pronunciation, EntryLexeme, LexemeBase
from etymmap.specific import EntryParserABC, Specific
from etymmap.utils import get_items, quick_plaintext
from etymmap.utils.section_text import SeqMap, tMaybeParsed
from . import consts
from .utils import any_pos, strip_etymology_header

RECONSTRUCTION_TITLE = re.compile(r"^Reconstruction:[^/]+/(.*)$")


class EntryParser(EntryParserABC):
    def clean_title(self, title: str, namespace: int) -> str:
        if namespace == 118:
            return re.sub(RECONSTRUCTION_TITLE, r"*\1", title)
        return title

    def parse_section(self, text: tMaybeParsed) -> SeqMap:
        """
        For English (and maybe most other) Wiktionaries, parse the sections using wtp

        :param text: the original wikitext, as string or parsed
        :return: the nested-dict sections mapping headings (lists of strings) to slices (pairs of ints) in the text
        """
        ret = SeqMap()
        if not text:
            return ret
        section_stack = []
        parsed_text = wtp.parse(text) if isinstance(text, str) else text
        for section in parsed_text.get_sections(include_subsections=False):
            # level shifted to 0, no 'holes' in hierarchy
            level = min(max(0, section.level - 2), len(section_stack))
            title = quick_plaintext(section.title).strip() or self.NO_HEADING
            while len(section_stack) > level:
                section_stack.pop()
            section_stack.append(title)
            ret[section_stack] = section.span
        return ret

    def make_gloss(self, text: tMaybeParsed, pos: str) -> Any:
        senseid = None
        labels, links, tags = [], [], []
        parsed = wtp.parse(text) if isinstance(text, str) else text
        for t in parsed.templates:
            tn = t.name.strip()
            if tn in consts.LABELS:
                labels.extend([a.value for a in t.arguments[1:]])
            elif tn == "senseid":
                assert senseid is None
                senseid = t.arguments[1].value
        for link in parsed.wikilinks:
            links.append(link.target)
        for tag in parsed.get_tags():
            tags.append(tag.string)
        return Gloss(
            pos, Specific.plain_text(parsed).strip(), senseid, labels, links, tags
        )

    def make_pronunciation(
        self,
        text: tMaybeParsed,
        _phonemic=re.compile(r"^/(.+)/$"),
        _phonetic=re.compile(r"^\[(.+)]$"),
    ) -> Any:
        ret = []
        parsed = wtp.parse(text) if isinstance(text, str) else wtp.parse(text)
        items = [
            i
            for list_ in parsed.get_lists()
            for i in get_items(list_, avoid_reparse=True)
        ] or [parsed]

        matches = [_phonemic, _phonetic]
        kinds = [Pronunciation.Kind.phonemic, Pronunciation.Kind.phonetic]
        for i in items:
            accent = None
            ipa = []
            kind = []
            for t in i.templates:
                if t.name == "IPA":
                    has_lang = next(
                        (True for a in t.arguments if a.name == "lang"), False
                    )
                    for a in t.arguments if has_lang else t.arguments[1:]:
                        if a.positional:
                            v = a.value.strip()
                            for p, k in zip(matches, kinds):
                                m = p.match(v)
                                if m:
                                    ipa.append(m.group(1))
                                    kind.append(k)
                                    break
                            else:
                                ipa.append(v)
                                kind.append(Pronunciation.Kind.plain)
                elif t.name == "a":
                    accent = t.arguments[0].value.strip()
            if ipa:
                if len(ipa) == 1:
                    ipa, kind = ipa[0], kind[0]
                ret.append(Pronunciation(ipa, accent, kind))
        return ret

    def make_lexemes(self, entry: Mapping) -> List[LexemeBase]:
        term, language = entry["title"], entry["language"]
        lexemes = []

        # current values
        sense_idx = 0
        pronunciation = []
        etymology = ""
        glosses = []
        etymid = None

        for section, section_text in zip(entry["sections"], entry["texts"]):
            subsection = section[-1]

            # Etymology section
            e = consts.ETYMOLOGY_SECTION.match(subsection)
            if e:
                if sense_idx or glosses or etymology or etymid:
                    lexemes.append(
                        EntryLexeme(
                            term,
                            language,
                            sense_idx,
                            pronunciation,
                            etymology,
                            glosses,
                            etymid,
                        )
                    )
                sense_idx = self.get_sense_index(match=e)
                # we do not clear the pronunciation here, as it might scope over all lexemes
                glosses = []
                section_text = strip_etymology_header(section_text).strip()
                if section_text:
                    etymology_parsed = wtp.parse(section_text)
                    etymid = next(
                        (
                            t.arguments[1].value
                            for t in etymology_parsed.templates[:5]
                            if t.name.strip() == "etymid"
                        ),
                        None,
                    )
                    etymology = Specific.plain_text(etymology_parsed).strip()

            # Definitions/ POS section
            elif any_pos.match(subsection):
                for list_ in wtp.parse(section_text).get_lists():
                    for item in get_items(list_, avoid_reparse=True):
                        glosses.append(self.make_gloss(item, subsection))

            # Pronunciation
            elif consts.WPRONUNCIATION == subsection:
                pronunciation = self.make_pronunciation(section_text)

        lexemes.append(
            EntryLexeme(
                term, language, sense_idx, pronunciation, etymology, glosses, etymid
            )
        )
        # sometimes, we have the indexing in the pronunciation and all etymologies have no index
        for i, lexeme in enumerate(lexemes):
            if lexeme.sense_idx == 0 and i > 0:
                lexeme._sense_idx = max(l.sense_idx for l in lexemes) + 1

        return lexemes

    def count_etymologies(self, sections: List[List[str]], texts: List[str]) -> int:
        c = 0
        for s in sections:
            if 1 < len(s) < 4 and consts.ETYMOLOGY_SECTION.match(s[-1]):
                c += 1
        return c

    def get_sense_index(self, section: List[str] = None, match=None) -> int:
        if not match:
            if not section:
                raise ValueError("Must either specify match or section")
            for ss in section:
                match = consts.ETYMOLOGY_SECTION.match(ss)
                if match:
                    break
            else:
                raise ValueError(f"No sense index for {section}")
        return int(match.group(1) or 1) - 1  # we start indexing at 0
