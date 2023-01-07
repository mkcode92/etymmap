import logging
from collections import Counter

import networkx as nx
from tqdm import tqdm

from etymmap.specific_en import consts
from etymmap.wiktionary import Wiktionary

logger = logging.getLogger("LanguageTree")


def make_language_tree(
    wiktionary: Wiktionary,
    templates=("inh", "inheritance", "root"),
    min_count=8,
    min_odds=0.8,
):
    is_older_counter = Counter()
    for template in tqdm(
        wiktionary.templates(consts.ETYMOLOGY_SECTION, template_types=templates),
        unit=" templates",
    ):
        try:
            tgt_language, src_language = [a.value for a in template.arguments[:2]]
            is_older_counter[(src_language, tgt_language)] += 1
        except ValueError:
            continue
    tree = nx.DiGraph()
    for langs, count in is_older_counter.items():
        reversed_count = is_older_counter.get((langs[1], langs[0]), 0)
        odds = count / (count + reversed_count)
        if (count + reversed_count >= min_count) and (odds > min_odds):
            tree.add_edge(*langs, odds=odds)
    for cycle in list(nx.simple_cycles(tree)):
        for n1, n2 in zip(cycle, cycle[1:] + cycle[:1]):
            if tree.has_edge(n1, n2):
                logger.debug(f"Removing cycle edge {n1}-{n2}[{tree[n1][n2]['odds']}].")
                tree.remove_edge(n1, n2)
    return nx.transitive_reduction(tree)
