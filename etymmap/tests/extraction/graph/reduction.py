import importlib.resources
import io
import unittest
from typing import List

import networkx as nx

from etymmap.graph import (
    Relation,
    RelationAttributes,
    RelationType,
    SingleMeaningStub,
    StoringReductionListener,
    Node,
)
from etymmap.graph import ReducedRelations


def n_nodes(n) -> List[Node]:
    return [SingleMeaningStub(f"w{i}", f"l{i}") for i in range(n)]


class ReducedRelationsTest(unittest.TestCase):
    def setUp(self):
        self.relation_store = ReducedRelations(StoringReductionListener())

    def test_origin_is_added(self):
        relation = Relation(
            SingleMeaningStub("w1", "l1"),
            SingleMeaningStub("w2", "l2"),
            RelationAttributes(RelationType.BORROWING),
        )
        self.relation_store.add(relation)
        graph = self.relation_store.finalize()
        self.assertEqual(2, len(graph.nodes))
        self.assertEqual(1, len(graph.edges))

    def test_sibling_is_added(self):
        relation = Relation(
            SingleMeaningStub("w1", "l1"),
            SingleMeaningStub("w2", "l2"),
            RelationAttributes(RelationType.CALQUE),
        )
        self.relation_store.add(relation)
        graph = self.relation_store.finalize()
        self.assertEqual(2, len(graph.nodes))
        self.assertEqual(1, len(graph.edges))

    def test_related_is_added(self):
        relation = Relation(
            *n_nodes(2),
            RelationAttributes(RelationType.RELATED),
        )
        self.relation_store.add(relation)
        graph = self.relation_store.finalize()
        self.assertEqual(2, len(graph.nodes))
        self.assertEqual(1, len(graph.edges))

    def test_more_specific_edges_are_inserted(self):
        src, tgt = n_nodes(2)
        self.relation_store.add(
            Relation(src, tgt, RelationAttributes(RelationType.RELATED))
        )
        self.relation_store.add(
            Relation(src, tgt, RelationAttributes(RelationType.LEARNED_BORROWING))
        )
        self.relation_store.add(
            Relation(src, tgt, RelationAttributes(RelationType.BORROWING))
        )
        graph = self.relation_store.finalize()
        self.assertEqual(1, len(graph.edges))
        edge_data = graph.get_edge_data(src, tgt)
        self.assertEqual(1, len(edge_data))
        self.assertIn(RelationType.LEARNED_BORROWING, edge_data)

    def test_related_edges_are_merged_with_reversed(self):
        src, tgt = SingleMeaningStub("w1", "l1"), SingleMeaningStub("w2", "l2")
        self.relation_store.add(
            Relation(src, tgt, RelationAttributes(RelationType.RELATED))
        )
        self.relation_store.add(
            Relation(tgt, src, RelationAttributes(RelationType.RELATED))
        )
        graph = self.relation_store.finalize()
        self.assertEqual(1, len(graph.edges))

    def test_sibling_edges_are_merged_with_reversed(self):
        src, tgt = n_nodes(2)
        self.relation_store.add(
            Relation(src, tgt, RelationAttributes(RelationType.COGNATE))
        )
        self.relation_store.add(
            Relation(tgt, src, RelationAttributes(RelationType.COGNATE))
        )
        graph = self.relation_store.finalize()
        self.assertEqual(1, len(graph.edges))

    def test_selfloops_are_ignored(self):
        src = tgt = n_nodes(1)[0]
        self.relation_store.add(
            Relation(src, tgt, RelationAttributes(RelationType.RELATED))
        )
        graph = self.relation_store.finalize()
        self.assertEqual(0, len(graph.edges))

    def test_incompatible_edges_are_both_kept(self):
        src, tgt = n_nodes(2)
        self.relation_store.add(
            Relation(src, tgt, RelationAttributes(RelationType.BORROWING))
        )
        self.relation_store.add(
            Relation(src, tgt, RelationAttributes(RelationType.EPONYM))
        )
        graph = self.relation_store.finalize()
        self.assertEqual(2, len(graph.edges))

    def test_remove_cycles(self):
        n1, n2, n3, n4 = n_nodes(4)
        attrs = RelationAttributes(RelationType.COMPOUND)
        for relation in [
            Relation(n1, n2, attrs),
            Relation(n2, n3, attrs),
            Relation(n3, n1, attrs),
            Relation(n3, n4, attrs),
        ]:
            self.relation_store.add(relation)
        self.relation_store.remove_cycles()
        self.assertEqual([(n3, n4)], list(self.relation_store.origin.edges))

    def test_basic_transitive_reduce(self):
        n1, n2, n3, n4 = n_nodes(4)
        attrs = RelationAttributes(RelationType.COMPOUND)
        for relation in [
            Relation(n1, n2, attrs),
            Relation(n2, n3, attrs),
            Relation(n3, n4, attrs),
            Relation(n1, n4, attrs),
        ]:
            self.relation_store.add(relation)
        self.relation_store.transitive_reduce_directed()
        self.assertSetEqual(
            {(n1, n2), (n2, n3), (n3, n4)}, set(self.relation_store.origin.edges)
        )

    def test_language_swap(self):
        self.relation_store.language_tree = nx.read_gpickle(
            io.BytesIO(
                importlib.resources.read_binary("etymmap.data", "langtree.gpickle")
            )
        )
        # ang < enm < en
        n1 = SingleMeaningStub("test", "en")
        n2 = SingleMeaningStub("test", "enm")
        n3 = SingleMeaningStub("test", "ang")
        self.relation_store.add(
            Relation(n1, n2, RelationAttributes(RelationType.HISTORICAL))
        )
        self.relation_store.add(
            Relation(n3, n1, RelationAttributes(RelationType.DERIVATION))
        )
        self.assertSetEqual(set(self.relation_store.origin.edges), {(n2, n1), (n3, n1)})
