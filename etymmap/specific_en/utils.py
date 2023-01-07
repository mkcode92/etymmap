import re

from . import consts

ETYMOLOGY_HEADER = re.compile(r"^\s*=+Etym[^=]+=+\s*")


def strip_etymology_header(t: str) -> str:
    return re.sub(ETYMOLOGY_HEADER, "", t)


any_pos = re.compile(
    "|".join(
        [
            *consts.WPOS,
            *consts.WMORPHEMES,
            *consts.WPHRASES,
        ]
    ),
    flags=re.IGNORECASE,
)

heuristic_pos = {
    re.compile(r"^to \w+([,;.] to \w+)*"): consts.TEMPLATE_POS.get("Verb"),
    re.compile(r"^(an?|the) \w+"): consts.TEMPLATE_POS.get("Noun"),
    re.compile(r"^[a-z]\w+ly"): consts.TEMPLATE_POS.get("Adverb"),
}


def get_heuristic_pos(pos: str) -> str:
    for pattern, representative in heuristic_pos.items():
        if pattern.match(pos):
            return representative
