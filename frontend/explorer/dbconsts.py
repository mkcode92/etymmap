import logging
import re

import networkx as nx

from etymmap.specific import Specific
from etymmap.specific_en import languages, configure

# configure English for Specific

configure()


class Consts:
    def __init__(self, db_languages, pos, gloss_labels, node_labels):
        """
        Values that are characteristic for the db and that are retrieved at startup
        """
        self.logger = logging.getLogger()
        self.pos = pos
        self.gloss_labels = gloss_labels
        self.node_labels = node_labels
        self.combined_language_tree = self.make_combined_tree(db_languages)
        self.languages = sorted(
            [self.to_display(*l) for l in self.combined_language_tree.nodes]
        )

    @classmethod
    def to_display(cls, name, code, is_family):
        if is_family == "F":
            return f"{name} ({code})*"
        return f"{name} ({code})"

    @classmethod
    def to_code(cls, repr_):
        return re.match(r".* \((.*)\)\*?$", repr_).group(1)

    def make_language_family_tree(self, db_languages):
        def get_family_code(name):
            codes = Specific.language_mapper.name2code(name, allow_ambiguity=True)
            fcodes = [c for c in codes if Specific.language_mapper.is_family(c)]
            if not fcodes:
                print(f"Not a family {name} ({fcodes}, {codes})")
                return codes[0]
            if len(fcodes) > 1:
                print(f"Ambiguous {name} ({fcodes})")
            return codes[0]

        families = nx.DiGraph()
        data_updater = languages.CachedLanguageDataUpdater()
        family_data = data_updater.make_family_data()
        language_data = {
            l: d
            for l, d in data_updater.make_language_data().items()
            if l in db_languages
        }
        for code, data in family_data.items():
            name = data["Canonical name"]
            parent = data["Parent family"]
            if name == parent:
                continue
            if parent:
                try:
                    families.add_edge(
                        (parent, get_family_code(parent), "F"), (name, code, "F")
                    )
                except KeyError as ke:
                    self.logger.warning(ke.args[0])
                    continue
            else:
                families.add_node((name, code, "F"))

        for code, data in language_data.items():
            try:
                if data.get("Parent"):
                    src = (
                        data["Parent"],
                        Specific.language_mapper.name2code(data["Parent"]),
                        "L",
                    )
                else:
                    src = data["Family"], get_family_code(data["Family"]), "F"
                tgt = (data["Canonical name"], code, "L")
                if src != tgt:
                    families.add_edge(src, tgt)
            except KeyError as ke:
                self.logger.warning(ke.args[0])
                continue

        keep = set()
        stack = [(d["Canonical name"], c, "L") for c, d in language_data.items()]
        while stack:
            l = stack.pop()
            if l in keep:
                continue
            elif l in families:
                keep.add(l)
                stack.extend(families.predecessors(l))
        families = families.subgraph(keep)
        return families

    def make_combined_tree(self, db_languages):
        family_tree = self.make_language_family_tree(db_languages)
        phylo_tree = nx.DiGraph(
            [
                (
                    (Specific.language_mapper.code2name(c1), c1, "L"),
                    (Specific.language_mapper.code2name(c2), c2, "L"),
                )
                for c1, c2 in languages.load_phylogenetic_tree()
                .subgraph(db_languages)
                .edges()
            ]
        )

        combined_tree = nx.transitive_reduction(
            nx.DiGraph(list(family_tree.edges) + list(phylo_tree.edges))
        )
        return combined_tree
