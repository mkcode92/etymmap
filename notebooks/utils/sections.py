import re
from collections import defaultdict, Counter
from typing import List

import wikitextparser as wtp
from tqdm import tqdm

from etymmap.graph import RelationType
from etymmap.specific import Specific
from etymmap.specific_en import consts
from etymmap.utils import tFlexStr
from etymmap.wiktionary import Wiktionary


def count_sections(wiktionary: Wiktionary):
    section_count = defaultdict(Counter)
    sections = re.compile("(etym|desc|deriv|related).*", re.I)
    for section, *_ in tqdm(wiktionary.sections(sections), total=2.34 * 10**6):
        subsection = section[-1]
        section_count[sections.match(subsection).group(1).lower()][subsection] += 1
    return section_count


def section_examples(wiktionary: Wiktionary, section: tFlexStr, n=3) -> List[str]:
    section_iter = iter(wiktionary.sections(section))
    return [next(section_iter)[1] for _ in range(n)]


def template_counts_by_section(wiktionary: Wiktionary):
    template_name_by_section = defaultdict(Counter)
    all_etym_sections = consts.ALL_ETYMOLOGY_SECTIONS
    for section, text, ctx in tqdm(
        wiktionary.sections(all_etym_sections), total=2.34 * 10**6
    ):
        parsed = wtp.parse(text)
        section_name = all_etym_sections.match(section[-1]).group(1)
        for template in parsed.templates:
            template_name_by_section[section_name][template.name.strip()] += 1
        template_name_by_section[section_name]["WIKILINK"] += len(parsed.wikilinks)
    return template_name_by_section


spec_types = ["origin", "sibling", "related", "stub", "unhandled"]


def template_spec_type(template: wtp.Template) -> str:
    if template.name.strip() in {"etystub", "nonlemma", "nonlemmas", "rfe"}:
        return "stub"
    try:
        type_ = Specific.template_handler.to_normalization(template).relation["type"]
        if type_.is_a(RelationType.ORIGIN):
            return "origin"
        elif type_.is_a(RelationType.SIBLING):
            return "sibling"
        else:
            return "related"
    except NotImplementedError:
        return "unhandled"
