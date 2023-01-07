import re

from etymmap.utils import Equivalent


def _make_template_pos(wpos, wmorphemes):
    template_pos = Equivalent()
    for pos in [*wpos, *wmorphemes]:
        template_pos.declare(pos, add_lower=True)
    # specific_en forms e.q. verbal suffix
    for pos in ["Verb", "Noun", "Participle"] + wmorphemes:
        template_pos.declare(pos, re.compile(f".* {pos.lower()}"), add=True)
    # enumerated
    for pos, short in [
        ("Verb", "v."),
        ("Noun", "n."),
        ("Adjective", "adj."),
        ("Suffix", "suf."),
    ]:
        template_pos.declare(pos, re.compile(f".*{short}.*"), add=True)

    template_pos.declare("Adjective", "a", "adj", "adjectives", add=True)
    template_pos.declare("Numeral", "number", "num", add=True)
    template_pos.declare("Participle", "past participle", add=True)
    template_pos.declare(
        "Verb",
        "verbs",
        "v",
        "transitive",
        "intransitive",
        re.compile(".* verb"),
        add=True,
    )
    template_pos.declare(
        "Noun",
        "n",
        "nouns",
        "plural",
        "genitive",
        "dative",
        "accusative",
        re.compile(r"n\.\(\d+\)"),
        add=True,
    )
    return template_pos


BASEURL = "https://en.wiktionary.org/wiki"

# https://en.wiktionary.org/wiki/Wiktionary:Namespace
WNAMESPACES = [*range(-2, 16), *range(90, 94), *range(100, 120), 828, 829]

LANGUAGE_TABLES = BASEURL + "/Wiktionary:List_of_languages"
LANGUAGE_FAMILIES = BASEURL + "/Wiktionary:List_of_families"
SPECIAL_LANGUAGE_TABLES = BASEURL + "/Wiktionary:List_of_languages/special"
LANGUAGE_DATA_MODULES = tuple(
    [
        BASEURL + "/Module:languages/" + s
        for s in [
            "data2",
            *[f"data3/{l}" for l in "abcdefghijklmnopqrstuvwxyz"],
            "datax",
        ]
    ]
)

# https://en.wiktionary.org/wiki/Wiktionary:Entry_layout#Part_of_speech
WPOS = [
    "Adjective",
    "Adverb",
    "Ambiposition",
    "Article",
    "Circumposition",
    "Classifier",
    "Conjunction",
    "Contraction",
    "Counter",
    "Determiner",
    "Definitions",  # for Chinese
    "Ideophone",
    "Interjection",
    "Noun",
    "Numeral",
    "Participle",
    "Particle",
    "Postposition",
    "Preposition",
    "Pronoun",
    "Proper noun",
    "Verb",
]
WMORPHEMES = [
    "Affix",
    "Circumfix",
    "Combining form",
    "Infix",
    "Interfix",
    "Prefix",
    "Root",
    "Suffix",
]
WPHRASES = ["Phrase", "Proverb", "Prepositional phrase"]
WCHARS = ["Han character", "Hanzi", "Kanji", "Hanja", "Romanization"]
WPRONUNCIATION = "Pronunciation"

ETYMOLOGY_SECTION = re.compile(r"Etym\D+(\d*)")
RELATED_TERMS = re.compile(r"Related.+")
DERIVED_TERMS = re.compile(r"Derived.+")
DESCENDANTS = re.compile(r"Descendants")
ALL_ETYMOLOGY_SECTIONS = re.compile("(Etym|Related|Derived|Descendants).*")

LABELS = {"lb", "lbl", "term-label", "tlb", "label"}

TEMPLATE_POS = _make_template_pos(WPOS, WMORPHEMES)
