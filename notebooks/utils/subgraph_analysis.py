from collections import Counter
from typing import Tuple

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
import tqdm
from pandas import DataFrame

from etymmap.extraction import EtymologyExtractor, SectionExtractor
from etymmap.graph import (
    LexemeBase,
    ReducedRelations,
    StoringReductionListener,
)
from etymmap.specific import Specific
from etymmap.specific_en.languages import load_phylogenetic_tree


def apply_extractor(
        *section_extractors: SectionExtractor,
        head: int = None,
        progress: bool = True,
        swap_historic_languages=False,
):
    """
    Collect the relations using a single extractor

    :param section_extractors:
    :param progress: show progress info (entry iterations)
    :param head: only process first <head> entries
    :param swap_historic_languages: if true, invert relations if they contradict the direction of the language tree
    :return: the EtymologyExtractor that performed the extraction
    """
    if swap_historic_languages:
        language_tree = load_phylogenetic_tree()
    else:
        language_tree = None
    extractor = EtymologyExtractor(
        *section_extractors,
        relation_store=ReducedRelations(
            reduction_listener=StoringReductionListener(), language_tree=language_tree
        ),
    )
    extractor.collect_relations(progress=progress, head=head)
    return extractor


def describe(graph: nx.DiGraph):
    """
    Stats + component analysis
    :param graph:
    :return: tuple of info, component_sizes, main_components
    """
    big_components = []
    component_sizes = []
    for comp in nx.algorithms.weakly_connected_components(graph):
        l = len(comp)
        component_sizes.append(l)
        big_components.append(comp)
        big_components = sorted(big_components, key=len, reverse=True)[:3]
    component_sizes = pd.Series(component_sizes)
    return (
        {
            "n_nodes": graph.number_of_nodes(),
            "n_edges": graph.number_of_edges(),
            "n_components": len(component_sizes),
            "component_size": {
                "mode": component_sizes.mode()[0],
                **component_sizes.agg(["mean", "min", "max"]).to_dict(),
                # expected value for the component size of a node
                "expected_size": (component_sizes ** 2).sum() / graph.number_of_nodes(),
            },
        },
        component_sizes,
        big_components,
    )


def show_component_sizes(component_sizes, bins=np.logspace(1, 6, 25)):
    component_sizes_per_node = Counter(
        {c: c * v for c, v in Counter(component_sizes).items()}
    ).elements()
    pd.Series(component_sizes_per_node).hist(bins=bins)
    plt.gca().set_xscale("log")


def show_languages_in_component(component, n=25):
    pd.Series(
        dict(
            Counter(
                n.language for n in component if isinstance(n, LexemeBase)
            ).most_common()[:n]
        )
    ).plot(kind="bar")


def language_counts(graph: nx.MultiDiGraph) -> pd.DataFrame:
    languages = pd.Series(
        Counter(l.language for l in graph if isinstance(l, LexemeBase))
    ).sort_values(ascending=False)
    ret = pd.concat([languages, (languages / languages.sum())], axis=1)
    ret.columns = ["count", "ratio"]
    langs = []
    for l in ret.index:
        try:
            langs.append(Specific.language_mapper.code2name(l))
        except KeyError:
            langs.append(l)
    ret.index = langs
    return ret


def in_out_degree_grid(graph: nx.MultiDiGraph) -> Tuple[dict, DataFrame]:
    """
    Make a matrix for the in-degree/out-degree histogram

    :param graph:
    :return:
    """
    degrees = {}
    for node, indeg in graph.in_degree:
        degrees[node.id] = indeg
    for node, outdeg in graph.out_degree:
        degrees[node.id] = degrees[node.id], outdeg
    degree_grid = (
        pd.Series(Counter(degrees.values())).unstack(level=1, fill_value=0).astype(int)
    )
    degree_grid.index.name = "in"
    degree_grid.columns = pd.Series(degree_grid.columns, name="out")
    return degrees, degree_grid


def redundancy(graph: nx.Graph, reduction_listener: StoringReductionListener):
    counts = reduction_listener.counts()
    redundant = counts["MERGE_MORE_SPECIFIC"] + counts["MERGE_EQUAL"]
    return redundant / (graph.number_of_edges() + redundant)


def shortest_paths_to_connected_nodes(source, graph, cutoff):
    node_shortest_paths = pd.Series(
        nx.single_source_shortest_path_length(graph, source, cutoff=cutoff),
        dtype=int,
    ).iloc[1:]
    return (source.id, 0 if len(node_shortest_paths) == 0 else node_shortest_paths.mean(), len(node_shortest_paths))


def shortest_paths(
        graph: nx.MultiDiGraph, cutoff=None, frac=1.0
):
    all_nodes = np.array(graph.nodes)
    if frac < 1:
        sample = np.random.choice(all_nodes, int(graph.number_of_nodes() * frac), replace=False)
    else:
        sample = all_nodes
    return pd.DataFrame.from_records(
        [shortest_paths_to_connected_nodes(node, graph, cutoff) for node in
         tqdm.tqdm(sample, total=len(sample), unit=" nodes")],
        columns=["node", "avg_shortest_path", "n_reachable_nodes"])


def get_overlap(
        graph1: nx.MultiDiGraph, graph2: nx.MultiDiGraph, n_examples=100
) -> Tuple[pd.DataFrame, dict]:
    examples = {
        "only_left_nodes": [],
        "only_right_nodes": [],
        "only_left_edges": [],
        "only_right_edges": [],
    }
    # node overlap
    intersection = only_left = 0
    nodes2 = {node.id for node in graph2.nodes}
    for n in (node.id for node in graph1.nodes):
        if n in nodes2:
            intersection += 1
            nodes2.remove(n)
        else:
            only_left += 1
            if len(examples["only_left_nodes"]) < n_examples:
                examples["only_left_nodes"].append(n)
    node_overlap = (intersection, only_left, len(nodes2))
    examples["only_right_nodes"] = list(nodes2)[:n_examples]
    del nodes2
    # edge overlap
    intersection = only_left = 0
    rels2 = set((n1.id, n2.id) for (n1, n2, type_) in graph2.edges)
    for n in ((n1.id, n2.id) for (n1, n2, type_) in graph1.edges):
        if n in rels2:
            intersection += 1
            rels2.remove(n)
        else:
            if len(examples["only_left_edges"]) < n_examples:
                examples["only_left_edges"].append(n)
            only_left += 1
    edge_overlap = (intersection, only_left, len(rels2))
    examples["only_right_edges"] = list(rels2)[:n_examples]
    rels2.clear()
    # typed edge overlap
    intersection = only_left = 0
    rels2 = {(n1.id, n2.id, reltype.name) for n1, n2, reltype in graph2.edges}
    for edge in ((n1.id, n2.id, reltype.name) for n1, n2, reltype in graph1.edges):
        if edge in rels2:
            intersection += 1
            rels2.remove(edge)
        else:
            only_left += 1
    edge_overlap_typed = (intersection, only_left, len(rels2))
    return (
        pd.DataFrame(
            {
                "nodes": node_overlap,
                "edges": edge_overlap,
                "edges_typed": edge_overlap_typed,
            },
            index=["intersection", "only_left", "only_right"],
        ),
        examples,
    )
