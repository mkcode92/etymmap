import re
from typing import List, Optional

from etymmap.graph.relation_types import RelationType
from etymmap.specific.templates import (
    LinkSemantics,
    LinkNormalization,
    TemplateParameter,
)
from . import consts
from .template_helper import (
    TemplatePreprocessor,
    SpecificTemplateHandler,
    MultipleTargets,
    DescendantsSemantics,
    AllTargetParameters,
    UnknownTarget,
    TargetWithSourceLang,
    PlainMultiLinks,
    CompositeTemplateHandler,
    default_params,
    default_renaming,
    multi_term_preprocessor,
)
from .utils import get_heuristic_pos

# implementing behaviour of
# https://en.wiktionary.org/wiki/Module:etymology
# https://en.wiktionary.org/wiki/Module:etymology/templates
from ..specific import Specific

etymology_templates = [
    *[
        SpecificTemplateHandler(
            *names,
            positional_args=("language", "language", "term", "alt", "t"),
            default_relation=rel_name,
        )
        for *names, rel_name in [
            ["derived", "der", "der+", RelationType.DERIVATION],
            ["inherited", "inh", "inh+", RelationType.INHERITANCE],
            ["borrowed", "bor", "bor+", RelationType.BORROWING],
        ]
    ],
    *[
        SpecificTemplateHandler(
            *names, positional_args=("language", "language", "term", "alt", "t")
        )
        for names in [
            ["learned borrowing", "lbor", "lbor+"],
            ["orthographic borrowing", "obor", "obor+"],
            ["semi-learned borrowing", "slbor", "slb", "slb+"],
            ["unadapted borrowing", "ubor", "ubor+"],
        ]
    ],
    SpecificTemplateHandler(
        "root",
        default_relation=RelationType.ROOT,
        positional_args=("language", "language"),
        preprocessor=multi_term_preprocessor,
        link_semantics=MultipleTargets(True),
        template2plaintext=lambda t: "",
    ),
    *[
        SpecificTemplateHandler(
            *names,
            positional_args=("language", "language", "term", "alt", "t"),
            relation_in_text=rel_in_text,
            lang_in_text=True,
        )
        for *names, rel_in_text in [
            ["calque", "cal", "clq", "calq", "calque of"],
            ["partial calque", "pclq", "partial calque of"],
            ["semantic loan", "sl", "sml", "semantic loan of"],
            ["phono-semantic matching", "psm", "phono-semantic matching of"],
        ]
    ],
    SpecificTemplateHandler(
        "desc",
        "desctree",
        "descendant",
        default_relation=RelationType.INHERITANCE,
        positional_args=("language", "term", "alt", "t"),
        link_semantics=DescendantsSemantics(),
        preprocessor=TemplatePreprocessor(
            params_keep=default_params.union(DescendantsSemantics.relation_flags).union(
                {"unc"}
            ),
            renaming={
                **default_renaming,
                **{c: "calque" for c in ["clq", "calq", "calque"]},
            },
        ),
    ),
    *[
        SpecificTemplateHandler(
            *names,
            default_relation=RelationType.RELATED,
            positional_args=("language", "term", "alt", "t"),
            link_semantics=AllTargetParameters(),
        )
        for names in [
            ["m", "m+", "langname-mention", "m-self", "mention"],
            ["l", "l-self", "ll", "link"],
        ]
    ],
    *[
        SpecificTemplateHandler(
            *names,
            positional_args=("language", "term", "alt", "t"),
            link_semantics=AllTargetParameters(),
            relation_in_text=rel_in_text,
        )
        for *names, rel_in_text in [
            ["clipping", "clipping of", "clipping of"],
            ["back-formation", "back-form", "backform", "bf", "back-formation of"],
        ]
    ],
    *[
        SpecificTemplateHandler(
            *names,
            positional_args=("language",),
            link_semantics=UnknownTarget(),
            template2plaintext=lambda t: text,
        )
        for *names, text in [
            ["onomatopoeic", "onom", "onomatopoeic"],
            ["unknown", "unk", "unknown"],
        ]
    ],
    *[
        SpecificTemplateHandler(
            *names,
            default_relation=default_rel,
            positional_args=("language", "term", "alt", "t"),
            link_semantics=AllTargetParameters(),
            relation_in_text=rel_in_text,
        )
        for *names, default_rel, rel_in_text in [
            ["short for", RelationType.SHORTENING, "short for"],
            ["abbrev", RelationType.ABBREV, "abbreviation of"],
            [
                "alternative form of",
                "alt form",
                RelationType.ALTFORM,
                "alternative form of",
            ],
        ]
    ],
    *[
        SpecificTemplateHandler(
            *names,
            positional_args=("language", "term", "alt", "t"),
            link_semantics=AllTargetParameters(),
            lang_in_text=True,
        )
        for names in [
            ["cognate", "cog"],
            ["noncognate", "noncog", "ncog"],
        ]
    ],
    SpecificTemplateHandler(
        "affix",
        "af",
        default_relation=RelationType.MORPHOLOGICAL,  # affix can also be a compound
        positional_args=("language",),
        link_semantics=MultipleTargets(),
        preprocessor=multi_term_preprocessor,
        multiple_joiner=" + ",
    ),
    *[
        SpecificTemplateHandler(
            *names,
            positional_args=("language",),
            link_semantics=MultipleTargets(),
            preprocessor=multi_term_preprocessor,
            multiple_joiner=" + ",
        )
        for names in [
            ["prefix", "pre"],
            ["confix", "con"],
            ["infix"],
            ["circumfix"],
            ["suffix", "suf"],
            ["compound", "com"],
            ["univerbation", "univ"],
        ]
    ],
    *[
        SpecificTemplateHandler(
            *names,
            positional_args=("language",),
            link_semantics=MultipleTargets(),
            preprocessor=multi_term_preprocessor,
            relation_in_text=rel_in_text,
            multiple_joiner=" and ",
        )
        for *names, rel_in_text in [
            ["blending", "blend", "blending of"],
            ["doublet", "dbt", "doublet of"],
        ]
    ],
    SpecificTemplateHandler(
        "named-after",
        default_relation=RelationType.EPONYM,
        positional_args=("language", "name"),
        link_semantics=TargetWithSourceLang(),
        preprocessor=TemplatePreprocessor(
            params_keep={
                "language",
                "name",
                "occ",
                "nat",
                "born",
                "died",
                "wplink",
            },
            renaming={"nationality": "nat", "occupation": "occ"},
        ),
        relation_in_text="named after",
    ),
    SpecificTemplateHandler(
        "xy-of-relation",
        re.compile(r".*[- ]of$"),
        default_relation=RelationType.RELATED,
        positional_args=("language", "term", "alt", "t"),
        link_semantics=AllTargetParameters(),
        relation_in_text=re.compile(r".*[- ]of$"),
    ),
]

related_derived_handlers = [
    SpecificTemplateHandler(
        *[f"{r}{d}" for r in ["rel", "col", "der"] for d in range(2, 5)],
        default_relation=RelationType.RELATED,
        link_semantics=PlainMultiLinks(),
        preprocessor=TemplatePreprocessor(
            {"language"}, {"lang": "language"}
        ),  # only keep positionals
    )
]

# this registers basic renderers for other known templates
template2plaintexthandlers = [
    SpecificTemplateHandler(
        "etystub",
        "nonlemmas",
        "nonlemma",
        "rfe",
        link_semantics=None,
        template2plaintext=lambda t: "",
    ),
    SpecificTemplateHandler(
        "senseid",
        "quote-text",
        link_semantics=None,
        template2plaintext=lambda t: "",
    ),
    SpecificTemplateHandler(
        "rfdef",
        link_semantics=None,
        template2plaintext=lambda t: "-- Definition requested --",
    ),
    SpecificTemplateHandler(
        "gloss",
        "gl",
        "non-gloss definition",
        "non-gloss",
        "n-g",
        "ngd",
        "defdate",
        # svedish templates
        re.compile("^sv-.*[- ]form"),
        link_semantics=None,
        template2plaintext=lambda t: Specific.plain_text(t.arguments[0]),
    ),
    SpecificTemplateHandler(
        *consts.LABELS,
        "topics",
        "top",
        link_semantics=None,
        template2plaintext=lambda t: f"({', '.join([Specific.plain_text(a) for a in t.arguments[1:]])})",
    ),
    SpecificTemplateHandler(
        "qual",
        "qualifier",
        "q",
        link_semantics=None,
        template2plaintext=lambda t: f"({', '.join([Specific.plain_text(a) for a in t.arguments])})",
    ),
    SpecificTemplateHandler(
        "ux",
        "uxi",
        link_semantics=None,
        template2plaintext=lambda t: f'Usage example: "{Specific.plain_text(t.arguments[1])}"',
    ),
    SpecificTemplateHandler(
        "vern",
        link_semantics=None,
        template2plaintext=lambda t: Specific.plain_text(t.arguments[0]),
    ),
    SpecificTemplateHandler(
        "taxlink",
        link_semantics=None,
        template2plaintext=lambda t: Specific.plain_text(t.arguments[1]),
    ),
    SpecificTemplateHandler(
        "given name",
        "surname",
        link_semantics=None,
        template2plaintext=lambda t: f"A {t.name}"
        + next(
            (
                f"(from {Specific.plain_text(a)})"
                for a in t.arguments
                if a.name == "from"
            ),
            "",
        ),
    ),
    SpecificTemplateHandler(
        "w",  # wikipedia
        link_semantics=None,
        template2plaintext=lambda t: Specific.plain_text(
            next((a for a in t.arguments if a.name == "1"), "")
        ),
    ),
    SpecificTemplateHandler(
        "wikipedia",  # makes a wikipedia box
        link_semantics=None,
        template2plaintext=lambda t: "",
    ),
    SpecificTemplateHandler(
        "sense",
        re.compile("sense.*"),
        link_semantics=None,
        template2plaintext=lambda t: f"{' '.join([Specific.plain_text(a) for a in t.arguments if a.positional])}",
    ),
    SpecificTemplateHandler(
        "etyl",
        link_semantics=None,
        template2plaintext=lambda t: code2name(Specific.plain_text(t.arguments[0])),
    ),
    SpecificTemplateHandler(
        "dercat",  # contains etymological information for source languages, but no lexemes
        link_semantics=None,
        template2plaintext=lambda t: "",
    ),
]


def code2name(code: str):
    try:
        return Specific.language_mapper.code2name(code)
    except KeyError:
        return code


class ArabicRoot(LinkSemantics):
    def __call__(
        self, default_relation: RelationType, template_args: List[TemplateParameter]
    ) -> LinkNormalization:
        """
        The positional arguments are the parts of the root
        """
        return LinkNormalization(
            {"type": default_relation},
            {},
            {"language": "ar", "term": " ".join(a for _, a in template_args)},
        )


class JapaneseLink(LinkSemantics):
    def __call__(
        self, default_relation: RelationType, template_args: List[TemplateParameter]
    ) -> LinkNormalization:
        tgt = {"language": "ja"}
        d = dict(template_args)
        if "linkto" in d:
            # if linkto is set, override term and make term alt form (for plain text)
            d["term"], d["alt"] = (
                d["linkto"],
                d["term"],
            )
            del d["linkto"]
        tgt.update(d)
        return LinkNormalization({"type": default_relation}, {}, tgt)


additional_handlers = [
    SpecificTemplateHandler(
        "ar-root",
        default_relation=RelationType.ROOT,
        link_semantics=ArabicRoot(),
    ),
    SpecificTemplateHandler(
        "ja-r",
        default_relation=RelationType.RELATED,
        positional_args=("term", "ascii", "t"),
        preprocessor=TemplatePreprocessor(
            {"linkto", *default_params}, default_renaming
        ),
        link_semantics=JapaneseLink(),
    ),
]


class EtymologyTemplateHandler(CompositeTemplateHandler):
    def __init__(self):
        super().__init__(
            *etymology_templates,
            *related_derived_handlers,
            *template2plaintexthandlers,
            *additional_handlers,
        )

    def determine_pos(
        self, template_pos: str = None, gloss: str = None
    ) -> Optional[str]:
        if not template_pos:
            if gloss:
                return get_heuristic_pos(gloss)
        else:
            # map to more canonical name
            return consts.TEMPLATE_POS.get(template_pos, template_pos)
