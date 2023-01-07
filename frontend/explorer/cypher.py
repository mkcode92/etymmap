from typing import List, Tuple

import networkx as nx

from components import NodeSelect, RelationSelect
from consts import LEFT, RIGHT, AND, relation_tree
from dbconsts import Consts
from utils import as_cypher_list


def expand_dag_data(explicit_nodes, tree):
    expanded = set()
    for node in explicit_nodes:
        for src, tgt in nx.dfs_edges(tree, node):
            expanded.add(src)
            expanded.add(tgt)
    return expanded


def expand_languages(selected_languages, dbconsts: Consts):
    return expand_dag_data(selected_languages, dbconsts.combined_language_tree)


def expand_relations(selected_relations):
    return expand_dag_data(selected_relations, relation_tree)


class NodeCypher:
    def __init__(self, var: str, values: dict, dbconsts: Consts, path: str = None):
        self.var = var
        self.values = values
        self.dbconsts = dbconsts
        self.path = path

    @property
    def pattern(self):
        return f"({self.var}:Word)"

    @property
    def filters(self) -> str:
        NID = NodeSelect.ID
        var = self.var
        values = self.values
        clauses = []

        term = values[NID.TERM_TEXT]
        cmp = "=~" if values[NID.TERM_REGEX] else "="
        if term:
            term_clause = f'{var}.term {cmp} "{values[NID.TERM_TEXT]}" OR {var}.name {cmp} "{values[NID.TERM_TEXT]}"'
            if values[NID.TERM_NOT]:
                term_clause = f"NOT ({term_clause}"
            clauses.append(term_clause)

        languages = [Consts.to_code(l) for l in values[NID.LANGUAGES] or []]
        if values[NID.LANGUAGE_CHILDREN]:
            languages = expand_languages(languages, self.dbconsts)
        language_invert = "NOT " if values[NID.LANGUAGES_NOT] else ""
        if languages:
            clauses.append(
                f"NOT EXISTS({var}.language) OR ({language_invert}{var}.language IN {as_cypher_list(languages)})"
            )

        sense_idx = values[NID.SENSE_IDX]
        if sense_idx is not None:
            clauses.append(f"{var}.sense_idx = {sense_idx}")

        labels = values[NID.LABELS]
        labels_not = values[NID.LABELS_NOT]
        labels_joiner = "ALL" if values[NID.LABELS_JOINER] == AND else "ANY"
        if labels:
            label_clause = (
                f"{labels_joiner}(label in LABELS({var}) WHERE label IN {labels})"
            )
            if labels_not:
                label_clause = "NOT " + label_clause
            clauses.append(label_clause)
        if not clauses:
            return ""
        node_filter = " AND ".join([f"({c})" for c in clauses])
        if self.path:
            return f"ALL({self.var} IN NODES({self.path}) WHERE {node_filter})"
        return node_filter

    def attrselect(self, keep: List[str]) -> Tuple[str, List]:
        rels = set()
        collect = []
        filter_vars = []
        NID = NodeSelect.ID
        if self.values[NID.POS]:
            rels.add("HAS_POS>")
            filter_vars.append(self.posvar)
            collect.append(f"collect(distinct {self.attrvar}.type) as {self.posvar}")
        elif self.values[NID.GLOSS]:
            rels.add("HAS_GLOSS>")
            filter_vars.append(self.glossvar)
            collect.append(f"collect({self.attrvar}.text) as {self.glossvar}")
        elif self.values[NID.GLOSS_LABELS]:
            rels.add("HAS_GLOSS>")
            filter_vars.append(self.glosslabelvar)
            collect.append(
                f"apoc.coll.flatten(collect({self.attrvar}.labels)) as {self.glosslabelvar}"
            )
        if not rels:
            return "", filter_vars
        rels = "|".join(rels)
        collect = ", ".join(keep + collect)
        return (
            "\n".join(
                [
                    f'CALL apoc.neighbors.athop({self.var}, "{rels}", 1)',
                    f"YIELD node as {self.attrvar}",
                    f"WITH {collect}",
                ]
            ),
            filter_vars,
        )

    @property
    def attrvar(self):
        return f"{self.var}_attrs"

    @property
    def posvar(self):
        return f"{self.var}_pos"

    @property
    def glossvar(self):
        return f"{self.var}_gloss"

    @property
    def glosslabelvar(self):
        return f"{self.var}_glosslabels"

    @property
    def attrfilter(self):
        NID = NodeSelect.ID
        values = self.values
        clauses = []
        pos = values[NID.POS]
        gloss = values[NID.GLOSS]
        cmp = "=~" if values[NID.GLOSS_REGEX] else "="
        glosslabels = values[NID.GLOSS_LABELS]
        if pos:
            # we compare a list of pos per etymology entry to a list of allowed pos
            # if negated return all nodes where any pos is not in the allowed list
            if values[NID.POS_NOT]:
                clauses.append(
                    f"ANY(p IN {self.posvar} WHERE NOT p IN {as_cypher_list(pos)})"
                )
            # else return all nodes where any pos is in the allowed list
            else:
                clauses.append(
                    f"ANY(p IN {self.posvar} WHERE p IN {as_cypher_list(pos)})"
                )

        if gloss:
            clauses.append(f'ANY(gloss in {self.glossvar} WHERE gloss {cmp} "{gloss}")')
        if glosslabels:
            clauses.append(
                f"ANY(gl IN {self.glosslabelvar} WHERE gl IN {as_cypher_list(glosslabels)})"
            )
        return " AND ".join(clauses)


class IDMatchCypher(NodeCypher):
    def __init__(self, var, id):
        super().__init__(var, None, None)
        self.id = id

    @property
    def filters(self):
        return f"ID({self.var}) = {self.id}"

    def attrselect(self, keep: List[str]):
        return "", keep

    @property
    def attrfilter(self):
        return ""


class RelationCypher:
    def __init__(self, var: str, values: dict):
        self.var = var
        self.values = values

    @property
    def filter(self):
        RID = RelationSelect.ID
        selected = self.values[RID.SELECT]
        if self.values[RID.TRANSITIVE]:
            selected = expand_relations(selected)
        exclude = as_cypher_list(["HAS_POS", "HAS_GLOSS", "HAS_PRONUC"])
        return (
            f"ALL({self.relvar} IN {self.var} WHERE TYPE({self.relvar}) IN {as_cypher_list(selected)} AND NOT "
            f"TYPE({self.relvar}) IN {exclude})"
        )

    @property
    def relvar(self):
        return f"{self.var}_i"

    @property
    def pattern(self):
        RID = RelationSelect.ID
        tail = "<" if self.values[RID.DIRECTION] == LEFT else ""
        head = ">" if self.values[RID.DIRECTION] == RIGHT else ""
        return f"{tail}-[{self.var}*..{self.depth}]-{head}"

    @property
    def depth(self):
        RID = RelationSelect.ID
        return self.values[RID.DEPTH]
