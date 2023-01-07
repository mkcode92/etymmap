# list of available graph layouts cytoscape.load_extra_layouts must be called
import json
import logging

import networkx as nx

from etymmap.graph import RelationType

LAYOUTS = {
    "dagre (TD)": json.dumps(
        {"name": "dagre", "rankDir": "TD", "nodeDimensionsIncludeLabels": True}
    ),
    "dagre (LR)": json.dumps(
        {"name": "dagre", "rankDir": "LR", "nodeDimensionsIncludeLabels": True}
    ),
    **{
        name: json.dumps({"name": name})
        for name in [
            "circle",
            "concentric",
            "breadthfirst",
            "cola",
            "euler",
            "spread",
        ]
    },
    "klay": json.dumps({"name": "klay", "nodeDimensionsIncludeLabels": True}),
}
DEFAULT_LAYOUT = "concentric"

NOT = "not"
REGEX = ".*"
TRANSITIVE = "⩾"
AND = "&"
OR = "|"
LEFT = "←"
RIGHT = "→"
UNDIRECTED = "⇌"
DETAILS = "🔬"
ADD = "➕"
RELOAD = "⟳"
DELETE = "🗑"
TREE = "🌲"
AGGREGATE = "Aggregate"
PROTECTED_NODE_LABELS = ["EtymologyEntry", "Entity", "NAE", "Multiword", "Wiktionary"]
NODE_COUNT_MESSAGE = "Displaying {} nodes"
NOTHING_FOUND = "No matches found"

SHOW_LANGUAGE_TREE = "Languages"
SHOW_RELATION_TREE = "Relation Types"

ONCLICK_LABELS = [SHOW_DETAILS, PRUNE, EXPAND] = "Show Details", "Prune", "Expand"
NODE_ID = "NODEID"

STATUS_STYLE_WARNING = dict(color="red", fontSize="small")
STATUS_STYLE_NORMAL = dict(fontSize="small")

logger = logging.getLogger("Resources")


def make_relation_tree(
    tree=RelationType.get_ontology(), graph=None, _m=None
) -> nx.DiGraph:
    _m = {r.value: r.name for r in RelationType if isinstance(r.value, str)}
    if graph is None:
        graph = nx.DiGraph()
    root, children = tree
    root = _m[root]
    for child in children:
        if isinstance(child, tuple):
            graph.add_edge(root, _m[child[0]])
            make_relation_tree(child, graph, _m)
        else:
            graph.add_edge(root, _m[child])
    return graph


relation_tree = make_relation_tree()
