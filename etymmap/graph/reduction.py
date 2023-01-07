import itertools
import logging
from collections import defaultdict
from enum import Enum
from typing import MutableMapping, Tuple

import tqdm
import networkx as nx
from networkx.algorithms import (
    transitive_reduction,
    difference,
    weakly_connected_components,
)
from networkx.algorithms.cycles import simple_cycles

from .nodes import Node
from .relation_types import RelationType
from .relations import RelationAttributes, Relation
from .utils import NoNodeAttrs, NodeDictFactoryNoAttrs


class ReductionListener:
    class Event(Enum):
        MERGE_EQUAL = 1
        MERGE_MORE_SPECIFIC = 2
        INCOMPATIBLE = 3
        SELFLOOP = 4
        CYCLES = 5
        TRANSITIVE_REDUCED = 6
        INTRA_COMPONENT_REDUCTION = 7
        HIST_LANGUAGE_SWAP = 8

    def __call__(
        self,
        event: Event,
        *types: RelationType,
        src: Node = None,
        tgt: Node = None,
        count: int = None,
    ):
        pass


class StoringReductionListener(ReductionListener):
    def __init__(self):
        self.events = {}

    def __call__(
        self,
        event: ReductionListener.Event,
        *types: RelationType,
        src: Node = None,
        tgt: Node = None,
        count: int = None,
    ):
        if types:
            key = types[0], *sorted(types[1:], key=lambda t: t.name)
            if src or tgt:
                self.events.setdefault(event, {}).setdefault(key, []).append((src, tgt))
            else:
                d = self.events.setdefault(event, {})
                try:
                    d[key] += 1
                except KeyError:
                    d[key] = 1
        elif count is not None:
            try:
                self.events[event] += count
            except KeyError:
                self.events[event] = count
        else:
            raise ValueError("Must either specify types or count")

    def counts(self):
        ret = {}
        for k, v in self.events.items():
            if isinstance(v, int):
                ret[k.name] = v
            elif isinstance(v, dict):
                ret[k.name] = sum(
                    v2 if isinstance(v2, int) else len(v2) for v2 in v.values()
                )
        return ret


class DirectedParallelRelationStore(nx.MultiDiGraph):
    node_dict_factory = NodeDictFactoryNoAttrs
    node_attr_dict_factory = NoNodeAttrs
    adjlist_outer_dict_factory = dict  # node -> next_node
    adjlist_inner_dict_factory = dict  # node -> [reltype -> relationattrs]
    # first had this implemented, but the MultiDiGraph implementation contains a bug and cannot deal with
    # two different kinds of mappings here :/
    edge_key_dict_factory = dict  # ParallelTypeDict  # reltype -> relationattrs
    edge_attr_dict_factory = dict  # RelationAttributes


class DirectedRelationStore(nx.DiGraph):
    node_dict_factory = NodeDictFactoryNoAttrs
    node_attr_dict_factory = NoNodeAttrs
    edge_attr_dict_factory = RelationAttributes


class ReducedRelations:
    def __init__(
        self, reduction_listener: ReductionListener = None, language_tree=None
    ):
        self.logger = logging.getLogger("Reduction")
        self.related: nx.DiGraph = DirectedRelationStore()
        self.sibling: nx.MultiDiGraph = DirectedParallelRelationStore()
        self.origin: nx.DiGraph = DirectedRelationStore()
        self.origin_cycles_and_parallel_edges: nx.MultiDiGraph = (
            DirectedParallelRelationStore()
        )
        self.reduction_listener = reduction_listener or ReductionListener()
        self.finalized = False
        self.language_tree = language_tree
        self._graph = DirectedParallelRelationStore()

    def add(self, relation: Relation) -> None:
        """
        Record a new relation and reduce incrementally

        * try to merge directed edges with parallel edges
        * try to merge undirected edges with parallel and reversed edges
        * in both cases, remove less specific_en candidates
        """
        if self.finalized:
            raise ValueError("Cannot add to finalized graph.")
        event = self.reduction_listener.Event
        src, tgt, reltype = relation.src, relation.tgt, relation.attrs.type

        # do not add self-loops
        if src == tgt:
            # do not add self loops
            self.reduction_listener(event.SELFLOOP, reltype, src=src)
            return

        if reltype.directed:
            self._add_directed(relation)
        elif reltype.is_a(reltype.SIBLING):
            self._add_sibling(relation)
        else:
            self._add_related(relation)

    def order_hist_accurate(
        self, src: Node, tgt: Node, type_: RelationType
    ) -> Tuple[Node, Node]:
        if type_.is_a(RelationType.HISTORICAL):
            try:
                src_lang, tgt_lang = src.language, tgt.language
                #  if there is a path, src lang tgt lang is older than src_lang
                _ = nx.shortest_path(self.language_tree, tgt_lang, src_lang)
                self.reduction_listener(
                    self.reduction_listener.Event.HIST_LANGUAGE_SWAP, count=1
                )
                return tgt, src
            except (AttributeError, nx.NetworkXNoPath, nx.NodeNotFound):
                pass
        return src, tgt

    def _add_directed(self, relation: Relation):
        """
        Add a directed relation

        * Remove parallel RELATED edges
        * Merge with parallel compatible edges, keep most specific_en type
        * Keep parallel incompatible edges

        :param relation:
        :return:
        """
        # try to remove cycles as early as possible
        event = self.reduction_listener.Event
        src, tgt, relation_attrs = relation.src, relation.tgt, relation.attrs
        reltype = relation_attrs.type

        if self.language_tree:
            src, tgt = self.order_hist_accurate(src, tgt, reltype)

        undirected = (src, tgt) if id(src) < id(tgt) else (tgt, src)

        # remove parallel related relations
        try:
            self.related.remove_edge(*undirected)
            self.reduction_listener(
                event.MERGE_MORE_SPECIFIC,
                reltype,
                RelationType.RELATED,
            )
        except nx.NetworkXError:
            pass

        parallel_edge_data = self.origin.get_edge_data(src, tgt)
        # we try to immediately reduce cycles in directed graph, as it has to be a DAG for transitive reduction
        anti_parallel_edge_data = self.origin.get_edge_data(tgt, src)
        more_parallel_edges = self.origin_cycles_and_parallel_edges.get_edge_data(
            src, tgt, default={}
        )

        if parallel_edge_data:
            merged = self.merge_if_possible(relation_attrs, parallel_edge_data)
            if not merged:
                for more_parallel_edge_data in more_parallel_edges.values():
                    if self.merge_if_possible(relation_attrs, more_parallel_edge_data):
                        return
                parallel_types = []
                if parallel_edge_data:
                    parallel_types.append(parallel_edge_data["type"])
                if more_parallel_edges:
                    parallel_types.extend(
                        [d["type"] for d in more_parallel_edges.values()]
                    )
                if parallel_types:
                    self.reduction_listener(
                        event.INCOMPATIBLE, reltype, *parallel_types
                    )
                self.origin_cycles_and_parallel_edges.add_edge(
                    src, tgt, reltype, **relation_attrs
                )
        elif anti_parallel_edge_data:
            # still not merged: either incompatible or 2-cycle
            self.origin_cycles_and_parallel_edges.add_edge(
                src, tgt, reltype, **relation_attrs
            )
        else:
            self.origin.add_edge(src, tgt, **relation_attrs)

    def merge_if_possible(self, update_attrs, existing_attrs) -> bool:
        """
        Merge update_attrs into existing_attrs

        :return: True iff the attrs were merged
        """
        event = self.reduction_listener.Event
        reltype, other_type = update_attrs["type"], existing_attrs["type"]
        if other_type.is_a(reltype):
            self.merge_relation_attrs(existing_attrs, update_attrs)
            if other_type == reltype:
                self.reduction_listener(event.MERGE_EQUAL, other_type, reltype)
            else:
                self.reduction_listener(event.MERGE_MORE_SPECIFIC, other_type, reltype)
            return True
        elif reltype.is_a(other_type):
            self.merge_relation_attrs(existing_attrs, update_attrs)
            existing_attrs["type"] = update_attrs["type"]
            self.reduction_listener(event.MERGE_MORE_SPECIFIC, reltype, other_type)
            return True
        return False

    def _add_sibling(self, relation):
        event = self.reduction_listener.Event
        src, tgt, relation_attrs = relation.src, relation.tgt, relation.attrs
        reltype = relation_attrs.type
        src, tgt = (src, tgt) if id(src) < id(tgt) else (tgt, src)

        # remove related relations
        try:
            self.related.remove_edge(src, tgt)
            self.reduction_listener(
                event.MERGE_MORE_SPECIFIC,
                reltype,
                RelationType.RELATED,
            )
        except nx.NetworkXError:
            pass
        try:
            self.merge_relation_attrs(self.sibling[src][tgt][reltype], relation_attrs)
        except KeyError:
            self.sibling.add_edge(src, tgt, reltype, **relation_attrs)

    def _add_related(self, relation: Relation):
        event = self.reduction_listener.Event
        src, tgt, relation_attrs = relation.src, relation.tgt, relation.attrs
        src, tgt = (src, tgt) if id(src) < id(tgt) else (tgt, src)
        # is there a origin relation between the nodes?
        attrs = self.origin.get_edge_data(src, tgt) or self.origin.get_edge_data(
            tgt, src
        )
        if not attrs:
            # is there any sibling relation between the nodes?
            all_attrs = self.sibling.get_edge_data(src, tgt)
            if all_attrs:
                attrs = next(iter(all_attrs.values()))
        if attrs:
            self.merge_relation_attrs(attrs, relation_attrs)
            self.reduction_listener(
                event.MERGE_MORE_SPECIFIC, attrs["type"], RelationType.RELATED
            )
            return
        try:
            self.merge_relation_attrs(self.related[src][tgt], relation_attrs)
            self.reduction_listener(event.MERGE_EQUAL, RelationType.RELATED)
        except KeyError:
            self.related.add_edge(src, tgt, **relation_attrs)

    @staticmethod
    def merge_relation_attrs(attrs1: MutableMapping, attrs2: RelationAttributes):
        # merge text
        if attrs1["text"]:
            if attrs2.text:
                attrs1["text"] = f"{attrs1['text']}; {attrs2.text}"
        elif attrs2.text:
            attrs1["text"] = attrs2.text
        attrs1["uncertain"] = attrs1["uncertain"] or attrs2.uncertain
        # todo merge remaining attrs

    def remove_cycles(self) -> None:
        """
        Makes self.origin cycle-free. Shifts data to self.origin_cycles_and_parallel_edges
        """
        self.logger.info("Remove cycles.")
        cycles = []
        for cycle in tqdm.tqdm(simple_cycles(self.origin)):
            cycles.append(cycle)
        n_cycles = len(cycles)
        self.reduction_listener(self.reduction_listener.Event.CYCLES, count=n_cycles)
        for cycle in cycles:
            for src, tgt in zip(cycle, cycle[1:] + cycle[:1]):
                try:
                    relation_attrs = self.origin[src][tgt]
                    self.origin_cycles_and_parallel_edges.add_edge(
                        src, tgt, relation_attrs.type, **relation_attrs
                    )
                    self.origin.remove_edge(src, tgt)

                except (
                    KeyError,
                    nx.NetworkXError,
                ):  # edge is part of more than one cycle
                    continue
        self.logger.info(f"Shelved {n_cycles} cycles from directed sub-graph.")

    def inplace_remove_cycles(self):
        """
        This is mostly copied from nx.simple_cycles with the differences:
        1. cycles are immediately removed, reducing the search for successive cycles
        2. cycles with len < 3 are ignored, as these are filtered at insertion
        """
        self.logger.info("Remove cycles in-place.")
        G = self.origin
        n_cycles = 0

        def _shelf_cycle(path):
            self.reduction_listener(self.reduction_listener.Event.CYCLES, count=1)
            for src, tgt in zip(path, path[1:] + path[:1]):
                try:
                    relation_attrs = G[src][tgt]
                    self.origin_cycles_and_parallel_edges.add_edge(
                        src, tgt, relation_attrs.type, **relation_attrs
                    )
                    G.remove_edge(src, tgt)
                except (
                    KeyError,
                    nx.NetworkXError,
                ):  # edge is part of more than one cycle
                    continue

        def _unblock(thisnode, blocked, B):
            stack = {thisnode}
            while stack:
                node = stack.pop()
                if node in blocked:
                    blocked.remove(node)
                    stack.update(B[node])
                    B[node].clear()

        # Johnson's algorithm requires some ordering of the nodes.
        # We assign the arbitrary ordering given by the strongly connected comps
        # There is no need to track the ordering as each node removed as processed.
        # Also we save the actual graph so we can mutate it. We only take the
        # edges because we do not want to copy edge and node attributes here.
        subG = type(G)(G.edges())
        # !only use with size > 2, as direct 2-loops are incrementally shelved during self.add
        sccs = [scc for scc in nx.strongly_connected_components(subG) if len(scc) > 2]

        # !1-loops are also incrementally excluded

        while sccs:
            scc = sccs.pop()
            sccG = subG.subgraph(scc)
            # order of scc determines ordering of nodes
            startnode = scc.pop()
            # Processing node runs "circuit" routine from recursive version
            path = [startnode]
            blocked = set()  # vertex: blocked from search?
            closed = set()  # nodes involved in a cycle
            blocked.add(startnode)
            B = defaultdict(set)  # graph portions that yield no elementary circuit
            stack = [(startnode, list(sccG[startnode]))]  # sccG gives comp nbrs
            while stack:
                thisnode, nbrs = stack[-1]
                if nbrs:
                    nextnode = nbrs.pop()
                    if nextnode == startnode:
                        # yield path[:]
                        n_cycles += 1
                        # for debug #todo remove
                        print(f"\r{n_cycles} cycles.", end="", flush=True)
                        _shelf_cycle(path)
                        closed.update(path)
                    #                        print "Found a cycle", path, closed
                    elif nextnode not in blocked:
                        path.append(nextnode)
                        stack.append((nextnode, list(sccG[nextnode])))
                        closed.discard(nextnode)
                        blocked.add(nextnode)
                        continue
                # done with nextnode... look for more neighbors
                if not nbrs:  # no more nbrs
                    if thisnode in closed:
                        _unblock(thisnode, blocked, B)
                    else:
                        for nbr in sccG[thisnode]:
                            if thisnode not in B[nbr]:
                                B[nbr].add(thisnode)
                    stack.pop()
                    path.pop()
            # done processing this node
            H = subG.subgraph(scc)  # make smaller to avoid work in SCC routine
            sccs.extend(
                scc for scc in nx.strongly_connected_components(H) if len(scc) > 2
            )
        self.logger.info(f"Shelved {n_cycles} cycles from directed sub-graph.")

    def transitive_reduce_directed(self, rm_cycles_in_place=True):
        """
        Performs transitive reduction on the directed part
        """
        self.logger.info("Apply transitive reduction.")
        if rm_cycles_in_place:
            self.inplace_remove_cycles()
        else:
            self.remove_cycles()
        removed = difference(self.origin, transitive_reduction(self.origin))
        self.logger.debug(f"Removed {len(removed.edges)} edges.")
        for src, tgt in removed.edges:
            self.reduction_listener(
                self.reduction_listener.Event.TRANSITIVE_REDUCED,
                self.origin[src][tgt]["type"],
                src=src,
                tgt=tgt,
            )
            self.origin.remove_edge(src, tgt)

    def reduce_unspecific(self):
        """
        Removes all RELATED edges that are (mabe transitively) expressed in the specific_en network
        :return:
        """
        self.logger.info("Prune redundant RELATED edges.")
        pruned = 0
        for component in itertools.chain(
            weakly_connected_components(self.origin),
            weakly_connected_components(self.sibling),
        ):
            # the edges that are within a component of a specific_en graph
            # i.e. they are transitively expressed through specific_en relations
            intra_component_edges = list(self.related.subgraph(component).edges)
            # # for e in intra_component_edges:
            # #    self.logger.debug(f"{e}: {nx.shortest_path(undirected, e[0], e[1])}")
            self.related.remove_edges_from(intra_component_edges)
            pruned += len(intra_component_edges)
        self.logger.debug(f"Pruned {pruned} edges.")
        self.reduction_listener(
            self.reduction_listener.Event.INTRA_COMPONENT_REDUCTION, count=pruned
        )

    def finalize(
        self, transitive_reduce=True, reduce_unspecific=True, rm_cycles_inplace=True
    ) -> nx.MultiDiGraph:
        """
        Merge all graphs to a MultiDiGraph, clear own state
        """
        if self.finalized:
            return self._graph
        if transitive_reduce:
            self.transitive_reduce_directed(rm_cycles_inplace)
        if reduce_unspecific:
            self.reduce_unspecific()
        self.logger.debug("Merging graphs.")
        for g in (self.related, self.origin):
            self._graph.add_edges_from(
                (u, v, d["type"], d) for u, v, d in g.edges(data=True)
            )
            g.clear()
        for g in (self.sibling, self.origin_cycles_and_parallel_edges):
            self._graph.add_edges_from(g.edges(keys=True, data=True))
            g.clear()
        return self._graph

    @property
    def graph(self):
        if self.finalized:
            return self._graph
        else:
            raise ValueError("Graph might be reduced. Call finalize first.")
