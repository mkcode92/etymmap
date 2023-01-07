import math
from collections import defaultdict
from typing import Union, Tuple, List, Dict, Iterable, Collection

import networkx as nx
from neo4j.graph import Node, Relationship

from etymmap.graph import RelationType
from utils import random_color


def element_id(element: dict) -> Union[str, Tuple[str, str]]:
    d = element["data"]
    try:
        return d["id"]
    except KeyError:
        return d["source"], d["target"]


def prune(clicked_element: dict, elements: List[dict]) -> Tuple[List[dict], int]:
    return remove_elements([{"data": clicked_element}], elements)


def to_cyto_elements(
    nodes: Iterable[Node],
    relations: Iterable[Relationship],
    source_ids: Collection[str],
) -> Tuple[List[dict], int]:
    source_ids = set(source_ids)

    node_data = []
    for node in nodes:
        if node.get("term"):
            data = parse_node(node)
        elif node.get("count_*"):
            data = parse_aggregation(node)
        elif node.get("name"):
            data = parse_entity(node)
        else:
            data = parse_phantom(node)
        d = {"data": data}

        if node.id in source_ids:
            d["classes"] = "source"
        elif node.get("count_*"):
            d["classes"] = "agg"
        node_data.append(d)

    relation_data = [
        {
            "data": parse_relation(r),
            "classes": "directed" if RelationType[r.type].directed else "",
        }
        for r in relations
    ]

    elements = [*node_data, *relation_data]
    n_elements = len(node_data)

    return elements, n_elements


def add_elements(
    new_elements: List[dict], current_elements: List[dict]
) -> Tuple[List[dict], int]:
    return combine_elements(new_elements, current_elements, False)


def remove_elements(
    del_elements: List[dict], current_elements: List[dict]
) -> Tuple[List[dict], int]:
    return combine_elements(del_elements, current_elements, True)


def combine_elements(
    change_elements: List[dict], current_elements: List[dict], remove=False
):
    change_nodes, change_edges, _ = split_nodes_edges(change_elements)
    current_nodes, current_edges, current_connected = split_nodes_edges(
        current_elements
    )

    if remove:
        for n in change_nodes:
            del current_nodes[n]
            if n in current_connected:
                for e in current_connected[n]:
                    del current_edges[e]
        for n in change_edges:
            del current_edges[n]
    else:
        current_nodes.update(change_nodes)
        current_edges.update(change_edges)

    nodes = list(current_nodes.values())
    edges = list(current_edges.values())

    return nodes + edges, len(nodes)


def split_nodes_edges(
    elements: List[dict],
) -> Tuple[Dict[str, dict], Dict[str, dict], Dict[str, List[str]]]:
    nodes = {}  # node.id -> node
    edges = defaultdict()  # rel.id, src.id, tgt.id -> rel
    connected = defaultdict(list)  # node.id -> rel.id
    for e in elements:
        d = e["data"]
        try:
            nodes[d["id"]] = e
        except KeyError:
            id_, source, target = d["rel_id"], d["source"], d["target"]
            edges[id_] = e
            connected[source].append(id_)
            connected[target].append(id_)
    return nodes, edges, connected


def parse_node(node: Node) -> dict:
    return {
        "id": str(node.id),
        "term": node.get("term"),
        "language": node.get("language"),
        "sense_idx": node.get("sense_idx"),
        "name": node.get("name"),
        "_color": random_color(node.get("language")),
    }


def parse_aggregation(node: Node) -> dict:
    aggregates = set()
    if node.get("language"):
        aggregates.add(node.get("language"))
    aggregates.update(node.labels)
    count = node.get("count_*")
    size = f"{100 * math.log10(9 + count)}%"
    return {
        "id": str(node.id),
        "term": "-".join(aggregates)[:15],
        "labels": list(node.labels),
        "language": node.get("language"),
        "_count": count,
        "_size": size,
        "_color": random_color(aggregates),
    }


def parse_entity(node: Node) -> dict:
    return {
        "id": str(node.id),
        "term": node.get("name"),
        "_color": random_color(node.get("name")),
        **{k: node.get(k) for k in ["born", "died", "occ", "wikipedia"]},
    }


def parse_phantom(node: Node) -> dict:
    return {"id": str(node.id), "term": "👹", "language": "?", "_color": (0, 0, 0)}


def parse_relation(relation: Relationship) -> dict:
    return {
        "type": relation.type,
        "id": str(relation.id),
        "source": str(relation.start_node.id),
        "target": str(relation.end_node.id),
        "unknown": relation.get("unknown", False),
        "text": relation.get("text", ""),
        "_color": random_color(relation.type),
        "_count": relation.get("count_*", 1),
    }


def convert_family_tree(graph: nx.DiGraph) -> List[dict]:
    def toid(name, code, f):
        return f"{code}-{f}"

    nodes, edges = [], []
    for n1, n2 in graph.edges():
        if n1 == n2:
            continue
        for n, c, f in (n1, n2):
            nodes.append({"data": {"id": toid(n, c, f), "label": n}, "classes": f})
        edges.append({"data": {"source": toid(*n1), "target": toid(*n2)}})
    return [*nodes, *edges]


def convert_relation_tree(graph: nx.DiGraph) -> List[dict]:
    nodes = [{"data": {"id": n, "label": n}} for n in graph.nodes]
    edges = [{"data": {"source": n1, "target": n2}} for n1, n2 in graph.edges()]
    return [*nodes, *edges]
