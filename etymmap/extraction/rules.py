import abc
import logging
import re
from collections import defaultdict
from importlib.resources import read_text
from typing import List, Union, Tuple

import wikitextparser as wtp

from etymmap.graph import RelationType
from etymmap.specific import LinkNormalization, Specific
from etymmap.specific_en.utils import strip_etymology_header
from etymmap.utils import (
    tMaybeParsed,
    nonoverlapping,
    make_parsed_subsection,
)

tSeq = List[Union[str, wtp.WikiText, Tuple, LinkNormalization]]


def to_sequence(text: tMaybeParsed) -> tSeq:
    """
    Transforms the text to a sequence in which markup elements are separated from text

    :param text:
    :return: A list of strings and wikitext elements
    """
    ret: tSeq = []
    parsed = wtp.parse(text) if isinstance(text, str) else text
    markup_elements = nonoverlapping(
        [
            *parsed.templates,
            *parsed.wikilinks,
            *parsed.get_bolds_and_italics(recursive=False),
            *parsed.comments,
            *parsed.get_tags(),
        ]
    )
    markup_offset = parsed.span[0]  # needed for parsed subsection text
    last_end = 0
    for e, r in zip(*markup_elements):
        start, end = e.span
        text = parsed.string[last_end - markup_offset : start - markup_offset].strip()
        if not markup_offset:
            text = strip_etymology_header(text).strip()
        if text:
            ret.append(text)
        last_end = end
        if isinstance(e, wtp.Comment):
            # ignore comments and tags
            pass
        elif isinstance(e, wtp.Tag):
            if e.name == "div":
                # we convert here to string because otherwise we get a recursion error
                ret.extend(to_sequence(e.parsed_contents.string))
        elif isinstance(e, wtp.Italic):
            ret.extend(
                [
                    ("I", "start"),
                    *to_sequence(make_parsed_subsection(e, 2, -2)),
                    ("I", "end"),
                ]
            )
        elif isinstance(e, wtp.Bold):
            ret.extend(
                [
                    ("B", "start"),
                    *to_sequence(make_parsed_subsection(e, 3, -3)),
                    ("B", "end"),
                ]
            )
        else:
            ret.append(e)
    text = parsed.string[last_end - markup_offset :].strip()
    if text:
        ret.append(text)
    return ret


class SequenceRule(abc.ABC):
    # the default name of the rule
    name = ""
    # a tuple of rule names that should be applied before the current one
    requires = ()

    def __init__(self):
        self.counter = 0
        self.logger = logging.getLogger(self.__class__.__name__)

    @abc.abstractmethod
    def __call__(self, seq: tSeq) -> tSeq:
        """
        Annotate or apply a rule on a sequence. The
        input chain may be modified in the process

        :return: the modified chain
        """
        return seq


class SequenceRules(SequenceRule):
    def __init__(self, *rules: SequenceRule):
        super().__init__()
        self.rules = []
        for rule in rules:
            for requirement in rule.requires:
                if not any(rule2.name == requirement for rule2 in self.rules):
                    raise ValueError(
                        f"Rule {rule.__class__.__name__} requires {requirement}"
                    )
            self.rules.append(rule)

    def __call__(self, seq):
        ret = seq
        for rule in self.rules:
            ret = rule(ret)
        return ret

    @property
    def counts(self):
        return {rule.name: rule.counter for rule in self.rules}


class PatternAnnotator(SequenceRule):
    def __init__(self, pattern: re.Pattern, name, match_as_value=True, group=0):
        super().__init__()
        self.pattern = pattern
        self.name = name
        self.match_as_value = match_as_value
        self.group = group

    def __call__(self, seq: tSeq) -> tSeq:
        inserts = []
        for i, e in enumerate(seq):
            if isinstance(e, str):
                matches = self.pattern.finditer(e)
                last_end = 0
                insert = []
                for match in matches:
                    self.counter += 1
                    before = e[last_end : match.start()].strip()
                    if before:
                        insert.append(before)
                    insert.append(
                        (self.name, match.group(self.group))
                        if self.match_as_value
                        else (self.name,)
                    )
                    last_end = match.end()
                if last_end:
                    after = e[last_end:].strip()
                    if after:
                        insert.append(after)
                    inserts.append((i, insert))
            elif isinstance(e, wtp.WikiLink):
                match = None
                if self.pattern.fullmatch(e.title):
                    match = e.title
                elif self.pattern.fullmatch(e.text or ""):
                    match = e.text
                if match:
                    self.counter += 1
                    inserts.append(
                        (
                            i,
                            (
                                [
                                    (self.name, match)
                                    if self.match_as_value
                                    else (self.name,)
                                ]
                            ),
                        )
                    )
        for i, elems in reversed(inserts):
            seq[i : i + 1] = elems
        return seq


class LanguageAnnotator(PatternAnnotator):
    def __init__(self, skip=()):
        all_language_names = sorted(
            set(
                [lang for lang in Specific.language_mapper.names if len(lang) > 2]
            ).difference(skip),
            key=len,
            reverse=True,
        )
        super().__init__(
            re.compile(r"\b(" + "|".join(all_language_names) + r")\b"), "Language"
        )


language_annotator = LanguageAnnotator(
    skip=(
        "The",
        "Are",
        "sign",
        "isolate",
        "mixed",
        "not a family",
        "constructed",
        "substrate",
    )
)
uncertain_annotator = PatternAnnotator(
    re.compile(r"\b(maybe|possibly|probably|perhaps)\b", re.I), "Uncertain"
)
from_annotator = PatternAnnotator(re.compile(r"\bfrom\b", re.I), "From")
plus_annotator = PatternAnnotator(re.compile(r"\+"), "Plus")
punct_annotator = PatternAnnotator(re.compile(r"([.,;!?]+)"), "Punct")
brackets_annotator = PatternAnnotator(re.compile(r"[()]"), "Bracket")
literally_annotator = PatternAnnotator(re.compile(r"literally", re.I), "Literally")
# this has many false positives
maybe_name_annotator = PatternAnnotator(
    re.compile(r".([A-Z][\w.]*(( van|of|de|von)\b)?( [A-Z][\w.]+)+)"), "Name?", group=1
)


class RelationAnnotator(SequenceRules):
    name = "Relation"

    def __init__(self):
        super().__init__()
        self.names2types = {
            re.compile(
                r"\b" + f"({'|'.join([*names, type_.name])})" + r"\b", re.I
            ): type_
            if type_ != RelationType.DERIVATION
            else RelationType.ORIGIN
            for type_, names in Specific.template_handler.get_relation_mapping().items()
            if type_
        }
        self.names2types[
            re.compile(r"shorten(end|ing)\b", re.I)
        ] = RelationType.SHORTENING
        self.names2types[
            re.compile(r"(related to|see|compare)\b", re.I)
        ] = RelationType.RELATED
        self.names2types[re.compile("named after", re.I)] = RelationType.EPONYM
        self.names2types[
            re.compile(
                r"\b((of|origin) )?(uncertain|unknown|unclear)( (origin|descent))?",
                re.I,
            )
        ] = RelationType.UNKNOWN
        self.names2types[
            re.compile(r"\b(onomato|imitat)[a-z]+\b", re.I)
        ] = RelationType.ONOM
        self.names2types[re.compile(r"abbreviation", re.I)] = RelationType.ABBREV
        self.names2types[re.compile(r"named for", re.I)] = RelationType.EPONYM

        self.rules = [
            PatternAnnotator(pattern, (self.name, relation))
            for pattern, relation in self.names2types.items()
        ]

    @property
    def counter(self):
        ret = defaultdict(list)
        for rule in self.rules:
            ret[rule.name[1]].append(rule.counter)
        return {k: sum(v) for k, v in ret.items()}

    @counter.setter
    def counter(self, _):
        pass


class XYAnnotator(PatternAnnotator):
    def __init__(self):
        self.xy_phrases = re.compile(
            r"\b("
            + "|".join(
                sorted(
                    [
                        phrase.strip()
                        for phrase in read_text("etymmap.data", "of-forms.txt").split(
                            "\n"
                        )
                        if phrase.strip()
                    ],
                    reverse=True,
                )
            )
            + r") of\b",
            re.I,
        )
        super().__init__(self.xy_phrases, "XYOf", group=1)


class WikipediaLinkAnnotator(SequenceRule):
    name = "Wiki"

    def __call__(self, seq: tSeq) -> tSeq:
        wikitemps = {"w", "wikipedia"}  # wikipedia template might be more complex
        for i, e in enumerate(seq):
            if (
                isinstance(e, wtp.Template)
                and e.name.strip() in wikitemps
                and e.arguments
            ):
                seq[i] = (
                    self.name,
                    e.arguments[0].value,
                    next((a.value for a in e.arguments if a.name == "lang"), "en"),
                )
                self.counter += 1
            elif isinstance(e, wtp.WikiLink):
                parts = e.title.split(":")
                if parts[0] == "w":
                    if len(parts) == 3:
                        lang, title = parts[1:]
                    elif len(parts) == 2:
                        lang, title = "en", parts[1]
                    else:
                        continue
                    seq[i] = (self.name, title, lang)
                    self.counter += 1
        return seq


class QuotesAnnotator(SequenceRule):
    name = "Quote"
    # maybe not the most efficient, but readable
    singleQuoteAnnotator = PatternAnnotator(re.compile("[\"“”‘`']+"), name)

    def __call__(self, seq: tSeq) -> tSeq:
        seq = self.singleQuoteAnnotator(seq)
        start = True
        for i, e in enumerate(seq):
            if isinstance(e, tuple):
                if e[0] == self.name:
                    seq[i] = (self.name, "start" if start else "end")
                    start = not start
                    self.counter += 1
        return seq


class ApplyTemplateNormalization(SequenceRule):
    name = "Templates"

    def __call__(self, seq: tSeq) -> tSeq:
        for i, e in enumerate(seq):
            if isinstance(e, wtp.Template):
                try:
                    seq[i] = Specific.template_handler.to_normalization(e)
                    self.counter += 1
                except (ValueError, NotImplementedError):
                    continue
        return seq


class ApplyStringTokenization(SequenceRule):
    name = "Tokenization"

    def __call__(self, seq: tSeq) -> tSeq:
        inserts = []
        for i, e in enumerate(seq):
            if isinstance(e, str):
                inserts.append((i, re.split(r"\s+", e)))
        for i, tokens in reversed(inserts):
            seq[i : i + 1] = tokens
            self.counter += 1
        return seq


def map_seq_to_plain_text(seq: tSeq):
    ret = []
    for e in seq:
        if isinstance(e, str):
            ret.append(e)
        elif isinstance(e, wtp.WikiText):
            ret.append(Specific.plain_text(e))
        elif isinstance(e, tuple):
            # quotes have start/ end markers
            if e[0] == "Quote":
                ret.append('"')
            # ignore markup, take match as string
            elif e[0] not in set("IB"):
                ret.append(e[1])
        elif isinstance(e, LinkNormalization):
            # this is not optimal
            ret.append(e.link_target["term"])
        else:
            ret.append(str(e))
    return " ".join(ret)


class MaybeMentionAnnotator(SequenceRule):
    name = "Mention?"

    def __call__(self, seq: tSeq) -> tSeq:
        """
        Converts a link or a italics/ bold phrase into (Mention?, phrase)
        """
        inserts = []
        skip = 0  # the last position that was included in the previous mention scope
        for i, e in enumerate(seq):
            if skip:
                skip -= 1
            elif isinstance(e, wtp.WikiLink):
                inserts.append((i, i + 1, [e]))
            elif e == ("I", "start") or e == ("B", "start"):
                try:
                    lastpos = seq.index((e[0], "end"), i + 1)
                    scope = seq[i + 1 : lastpos]
                    inserts.append((i, lastpos + 1, scope))
                    skip = lastpos + 1 - i
                except ValueError:
                    self.logger.warning(f"Unexpected missing end: {seq}")
        for i, end, scope in reversed(inserts):
            if scope:
                self.counter += 1
                replace = [(self.name, map_seq_to_plain_text(scope))]
                seq[i:end] = replace
        return seq


class MaybeGlossAnnotator(SequenceRule):
    name = "Gloss?"

    requires = ("Quote", "Bracket", "Literally")
    mentions_skipped = 0

    def __call__(self, seq):
        """
        Converts a bracketed and/or quoted phrase into (Gloss?, text)
        """
        inserts = []
        skip = 0
        for i, e in enumerate(seq[:-2]):
            if skip:
                skip -= 1
            elif e == ("Bracket", "("):
                try:
                    lastpos = seq.index((e[0], ")"), i + 1)
                except ValueError:
                    continue
                # get scope and strip brackets and maybe quotes
                scope = seq[
                    i
                    + (2 if seq[i + 1] == ("Quote", "start") else 1) : lastpos
                    - (1 if seq[lastpos - 1] == ("Quote", "end") else 0)
                ]
                inserts.append(
                    (
                        i,
                        lastpos + 1,
                        scope,
                    )
                )
                skip = lastpos + 1 - i

            elif e == ("Quote", "start"):
                try:
                    lastpos = seq.index(("Quote", "end"), i + 1)
                except ValueError:
                    continue
                scope = seq[i + 1 : lastpos]
                inserts.append((i, lastpos + 1, scope))
                skip = lastpos + 1 - i

        for i, end, scope in reversed(inserts):
            if scope:
                self.counter += 1
                replace = [(self.name, map_seq_to_plain_text(scope))]
                seq[i:end] = replace
        return seq


class MentionRule(SequenceRule):
    name = "Mention"
    requires = (
        "Mention?",
        "Gloss?",
        "Language",
        "Literally",
        "Punct",
        "Plus",
        "Templates",
        "Tokenization",
    )

    def __init__(self, left_ctx=2, right_ctx=3):
        """
        Combine language, mention?, gloss? and literally annotations into mentions

        :param left_ctx: the context length to the left (in tokens/ wikitext elements)
        :param right_ctx: the context length to the right
        """
        super().__init__()
        self.left_ctx = left_ctx
        self.right_ctx = right_ctx

    def __call__(self, seq: tSeq) -> tSeq:
        """
        Combine a Mention? and a Gloss? into a Mention

        Optionally add Language or Literal meaning

        :param seq:
        :return:
        """
        inserts = []
        skip = 0
        for i, e in enumerate(seq):
            if skip:
                skip -= 1
                continue
            elif isinstance(e, tuple) and e[0] == "Mention?":
                mention = {"term": e[1]}
            elif (
                isinstance(e, LinkNormalization)
                and e.relation["type"] == RelationType.RELATED
            ):
                mention = e.link_target
            else:
                continue

            # the offsets for inclusion constituents
            left_offset = i
            right_offset = i + 1

            # search language to the left, from previous position up to left_ctx positions
            search_in = reversed(seq[max(i - self.left_ctx, 0) : i])
            for j, e2 in enumerate(search_in):
                if isinstance(e2, tuple):
                    if e2[0] == "Language":
                        mention["language"] = e2[1]
                        left_offset -= j + 1
                        break
                    elif e2[0] in {"Plus", "Punct"}:
                        break

            literally = False

            # search literally/ gloss to the right, from next position up to right ctx_positions
            search_in = seq[i + 1 : min(i + 1 + self.right_ctx, len(seq))]
            for j, e2 in enumerate(search_in):
                if isinstance(e2, tuple):
                    if e2[0] == "Literally":
                        literally = True
                    elif e2[0] == "Gloss?":
                        mention["lit" if literally else "t"] = e2[1]
                        right_offset += j + 1
                        break
                    elif e2[0] in {"Mention?", "Plus"}:
                        break

            inserts.append((left_offset, right_offset, [(self.name, mention)]))
            skip = right_offset - i - 1

        for i, e, mention in reversed(inserts):
            self.counter += 1
            seq[i:e] = mention
        return seq


class CompoundRule(SequenceRule):
    name = "CompoundRule"
    requires = ("Mention", "Plus", "Templates", "Tokenization")

    def __init__(self, ctx=4):
        super().__init__()
        self.ctx = ctx

    def __call__(self, seq: tSeq) -> tSeq:
        """ "
        Combines Mentions joined by a plus to a affix relation
        """
        inserts = []
        skip = 0
        for i, e in enumerate(seq):
            if skip:
                skip -= 1
            elif e == ("Plus", "+"):
                left = right = 0
                mentions = []
                # search left for exactly one mention
                for j, e2 in enumerate(reversed(seq[max(0, i - self.ctx) : i])):
                    if isinstance(e2, tuple):
                        if e2[0] == "Mention":
                            mentions.append(e2[1])
                            left = j + 1
                        break  # break on every other annotation
                    elif isinstance(e2, LinkNormalization):
                        if e2.relation["type"] == RelationType.RELATED:
                            mentions.append(e2.link_target)
                            left = j + 1
                            break
                        else:
                            self.logger.debug(
                                "There should not be specific_en templates next to '+'"
                            )
                        break

                # search right for one or more mentions
                ctx = self.ctx
                for j, e2 in enumerate(seq[i + 1 :]):
                    if not ctx:
                        break
                    if isinstance(e2, tuple):
                        if e2[0] == "Mention":
                            mentions.append(e2[1])
                            right = j + 1
                        elif e2[0] == "Plus":
                            # if more than two mentions are joined, reset the context limits
                            ctx = self.ctx + 1
                    elif isinstance(e2, LinkNormalization):
                        if e2.relation["type"] == RelationType.RELATED:
                            mentions.append(e2.link_target)
                            right = j + 1
                        else:
                            self.logger.debug(
                                f"There should not be specific_en templates next to '+': {e2}"
                            )
                    ctx -= 1
                if left and right:
                    inserts.append((i - left, i + right, mentions))
                    skip = right - i - 1
                elif left or right:
                    self.logger.debug("Missed +-Combination at " + str(seq))

        for i, e, m in reversed(inserts):
            self.counter += 1
            seq[i:e] = [
                LinkNormalization(
                    {"type": RelationType.MORPHOLOGICAL}, link_target=tuple(m)
                )
            ]
        return seq


class RelationRule(SequenceRule):
    name = "RelationRule"

    requires = ("Mention", "XYOf", "Relation", "Tokenization")

    def __init__(self, ctx=3):
        super().__init__()
        self.ctx = ctx

    def __call__(self, seq: tSeq) -> tSeq:
        """
        Combines a relation name or a xyof annotation and a adjacent mention into a LinkNormalization.
        Also, makes adjacent LinkNormalizations with RelationType RELATED more specific_en
        """
        inserts = []
        skip = False
        for i, e in enumerate(seq):
            if skip:
                skip -= 1
            elif isinstance(e, tuple):
                if e[0] == "Relation":
                    relation = {"type": e[1]}
                elif e[0] == "XYOf":
                    relation = {"type": RelationType.ORIGIN, "text": e[1]}
                else:
                    continue
                for j, e2 in enumerate(seq[i + 1 : min(len(seq), i + 1 + self.ctx)]):
                    if isinstance(e2, tuple):
                        if e2[0] == "Mention":
                            inserts.append(
                                (
                                    i,
                                    i + j + 1,
                                    LinkNormalization(relation, link_target=e2[1]),
                                )
                            )
                            skip = j + 1
                            break
                        elif e2[0] == "Plus":
                            break
                    elif isinstance(e2, LinkNormalization):
                        if e2.relation["type"] == RelationType.RELATED:
                            e2.relation.update(relation)
                            inserts.append((i, i + j + 1, LinkNormalization))
                            skip = j + 1
                            break
        for i, j, l in reversed(inserts):
            self.counter += 1
            seq[i:j] = [l]
        return seq


class FromRule(SequenceRule):
    name = "FromRule"
    requires = ("Mention", "From", "Punct")

    def __init__(self, ctx=2):
        super().__init__()
        self.ctx = ctx

    def __call__(self, seq: tSeq) -> tSeq:
        """
        Creates ORIGIN relations with mentions in context
        """
        inserts = []
        skip = 0
        for i, e in enumerate(seq):
            if skip:
                skip -= 1
            if isinstance(e, tuple) and e[0] == "From":
                for j, e2 in enumerate(seq[i + 1 : min(len(seq), i + self.ctx + 1)]):
                    if isinstance(e2, tuple):
                        if e2[0] == "Mention":
                            inserts.append(
                                (
                                    i,
                                    i + j + 2,
                                    LinkNormalization(
                                        {"type": RelationType.ORIGIN}, link_target=e2[1]
                                    ),
                                )
                            )
                            skip = j + 1
                        elif e2[0] == "Punct":
                            break
                    elif (
                        isinstance(e2, LinkNormalization)
                        and e2.relation["type"] == RelationType.RELATED
                    ):
                        self.counter += 1
                        e2.relation["type"] = RelationType.ORIGIN
        for i, e, ln in reversed(inserts):
            self.counter += 1
            seq[i:e] = [ln]
        return seq


class NamedAfterRule(SequenceRule):
    name = "NamedAfter"
    requires = ("Mention", "Wiki", "Name?", "Relation", "Punct")

    def __init__(self, ctx=8):
        self.ctx = ctx
        super().__init__()

    def __call__(self, seq: tSeq) -> tSeq:
        """
        Combine named after with wikilink, Name? or Mention
        """
        inserts = []
        skip = 0
        for i, e in enumerate(seq):
            if skip:
                skip -= 1
            elif (
                isinstance(e, tuple)
                and e[0][0] == "Relation"
                and e[0][1] == RelationType.EPONYM
            ):
                for tag in ["Wiki", "Name?"]:
                    if skip:
                        break
                    for j, e2 in enumerate(
                        seq[i + 1 : min(i + self.ctx + 1, len(seq))]
                    ):
                        if isinstance(e2, tuple):
                            if e2[0] == tag:
                                inserts.append(
                                    (
                                        i,
                                        i + j + 2,
                                        LinkNormalization(
                                            relation={"type": RelationType.EPONYM},
                                            link_target={"name": e2[1]},
                                        ),
                                    )
                                )
                                skip = j + 1
                                break
                            elif e2[0] == "Punct" and e2[1] == ".":
                                break
        for i, j, l in reversed(inserts):
            self.counter += 1
            seq[i:j] = [l]
        return seq


class EtylMentionRule(SequenceRule):
    name = "EtylRule"
    requires = ("Mention", "Templates")

    def __call__(self, seq: tSeq) -> tSeq:
        """
        Casts adjacent LinkNormalizations to origin and sets language parameter
        """
        for i, e in enumerate(seq[:-1]):
            if isinstance(e, wtp.Template) and e.name.strip() == "etyl":
                next_ = seq[i + 1]
                if (
                    isinstance(next_, LinkNormalization)
                    and next_.relation["type"] == RelationType.RELATED
                ):
                    next_.relation["type"] = RelationType.ORIGIN
                    next_.link_target["language"] = e.arguments[0].value
                    self.counter += 1
                elif isinstance(next_, tuple) and next_[0] == "Mention":
                    mention_dict = next_[1]
                    mention_dict["language"] = e.arguments[0].value
                    seq[i + 1] = LinkNormalization(
                        relation={"type": RelationType.ORIGIN}, link_target=mention_dict
                    )
                    self.counter += 1
        return seq


class UncertainRule(SequenceRule):
    name = "UncertainRule"
    requires = ("Uncertain",)

    def __init__(self, ctx=3):
        super().__init__()
        self.ctx = ctx

    def __call__(self, seq: tSeq) -> tSeq:
        """
        Add uncertain flag to LinkNormalization within context
        """
        skip = 0
        for i, e in enumerate(seq[:-1]):
            if skip:
                skip -= 1
            elif isinstance(e, tuple) and e[0] == "Uncertain":
                for j, e2 in enumerate(seq[i + 1 : min(len(seq), i + self.ctx + 1)]):
                    if isinstance(e2, LinkNormalization):
                        e2.relation["uncertain"] = True
                        skip = j + 1
                        self.counter += 1
                        break
        return seq


class MentionFallback(SequenceRule):
    name = "MentionFallback"
    requires = ("Mention",)

    def __call__(self, seq: tSeq) -> tSeq:
        """
        Transforms mentions to related links
        """
        for i, e in enumerate(seq[:-1]):
            if isinstance(e, tuple) and e[0] == "Mention":
                seq[i] = LinkNormalization(
                    {"type": RelationType.RELATED}, link_target=e[1]
                )
                self.counter += 1
        return seq


default_rules = SequenceRules(
    language_annotator,
    maybe_name_annotator,
    uncertain_annotator,
    WikipediaLinkAnnotator(),
    RelationAnnotator(),
    XYAnnotator(),
    literally_annotator,
    QuotesAnnotator(),
    brackets_annotator,
    punct_annotator,
    from_annotator,
    plus_annotator,
    MaybeMentionAnnotator(),
    MaybeGlossAnnotator(),
    ApplyTemplateNormalization(),
    ApplyStringTokenization(),
    MentionRule(),
    CompoundRule(),
    FromRule(),
    RelationRule(),
    NamedAfterRule(),
    EtylMentionRule(),
    MentionFallback(),
    UncertainRule(),
)
