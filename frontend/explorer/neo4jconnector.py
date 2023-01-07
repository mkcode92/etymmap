import logging
from collections import defaultdict
from typing import List, Tuple

import neo4j
from neo4j.graph import Relationship, Node

from components import RelationSelect, NodeSelect
from consts import PROTECTED_NODE_LABELS
from cypher import NodeCypher, RelationCypher, IDMatchCypher
from dbconsts import Consts
from utils import as_cypher_list


class Neo4jConfig:
    def __init__(self, uri: str, database: str, auth, query_timeout=10):
        self.uri = uri
        self.database = database
        self.auth = auth
        self.query_timeout = query_timeout

    def __repr__(self):
        return f"[{self.uri}/{self.database}, auth: {self.auth}]"


default_config = Neo4jConfig(
    uri="neo4j://0.0.0.0:7687",
    database="etymmap",
    auth=("neo4j", "neo4j123"),
    query_timeout=10,
)


class SearchTooBroad(BaseException):
    pass


class EtymGraphSession:
    def __init__(self, session: neo4j.Session):
        self.session = session
        self.logger = logging.getLogger(str(self))

    def __enter__(self):
        self.session.__enter__()
        return self

    def __exit__(self, *args, **kwargs):
        self.session.__exit__(*args, **kwargs)

    def cypher(self, cypher: str):
        self.logger.debug(cypher)
        yield from self.session.run(cypher)

    def simple_query(
        self, term: str, limit: int, id: int
    ) -> Tuple[Tuple, List[Relationship], Tuple, str]:
        """
        Just match the term and find the neighbours
        """
        if id is None:
            condition = f'WHERE source.term = "{term}" OR source.name = "{term}"'
        else:
            condition = f"WHERE ID(source) = {id}"
        cypher = "\n".join(
            [
                f"MATCH path=(source:Word)--(:Word)",
                condition,
                f"WITH source, path",
                f"LIMIT {limit}",
                f"WITH apoc.agg.graph(path) as subgraph, COLLECT(DISTINCT ID(source)) as sources",
                f"RETURN subgraph.nodes, subgraph.relationships, sources",
            ]
        )
        return (*list(self.cypher(cypher))[0], cypher)

    def advanced_query(
        self,
        source_select: dict,
        subgraph_select: dict,
        target_select: dict,
        relationship_select: dict,
        dbconsts: Consts,
        node_id: int = None,
    ):
        """
        Find a subgraph around a set of source nodes

        :param source_select: node filter for the start of the search
        :param subgraph_select: filter for all nodes
        :param target_select: node filter for the end of the search
        :param relationship_select: filter for the relations
        :return:
        """
        return self.pattern_query(
            source_select,
            subgraph_select,
            target_select,
            relationship_select,
            dbconsts,
            node_id,
        )

    def pattern_query(
        self,
        source_select: dict,
        subgraph_select: dict,
        target_select: dict,
        relationship_select: dict,
        dbconsts: Consts,
        node_id: int = None,
    ) -> Tuple[List[Node], List[Relationship], List[int], str]:
        RID = RelationSelect.ID
        search_depth = relationship_select[RID.DEPTH]

        node_select = (
            [source_select, subgraph_select, target_select]
            if search_depth
            else [source_select]
        )
        if node_id is None and not any(
            [NodeSelect.has_any_value(v) for v in node_select]
        ):
            raise SearchTooBroad("Query too broad - no node restriction")

        pathvar = "path"
        source_cypher, subgraph_cypher, target_cypher = [
            NodeCypher("source", source_select, dbconsts)
            if node_id is None
            else IDMatchCypher("source", node_id),
            NodeCypher("node", subgraph_select, dbconsts, path=pathvar),
            NodeCypher("target", target_select, dbconsts),
        ]

        path_cypher = RelationCypher("rels", relationship_select)

        filters = [source_cypher.filters]
        if search_depth:
            filters.extend(
                [
                    f"ALL(n in NODES({pathvar}) WHERE n:Word)",
                    subgraph_cypher.filters,
                    target_cypher.filters,
                ]
            )
            if relationship_select[RID.SELECT]:
                filters.append(path_cypher.filter)
        filters = [f for f in filters if f]

        filters = (
            ["WHERE " + "\nAND ".join([f"({f})" for f in filters])] if filters else []
        )

        keepvars = (
            [source_cypher.var, target_cypher.var, pathvar]
            if search_depth
            else [source_cypher.var]
        )
        allattrselect = []
        allattrfilter = []
        for cypher in [source_cypher, target_cypher]:
            attrselect, attrvars = cypher.attrselect(keepvars)
            keepvars += attrvars
            if attrselect:
                allattrselect.append(attrselect)
                allattrfilter.append(cypher.attrfilter)

        attrfilters = "\nAND ".join(allattrfilter)
        if attrfilters:
            attrselect = [
                "\n".join(allattrselect),
                f"WHERE {attrfilters}",
            ]

        limit = relationship_select[RID.LIMIT]
        limit_clause = (
            f"WITH {source_cypher.var}, {pathvar}"
            if search_depth
            else f"WITH {source_cypher.var}"
        )
        limit_clause += f"\nlimit {limit}"

        if not search_depth:
            cypher = "\n".join(
                [
                    f"MATCH {source_cypher.pattern}",
                    *filters,
                    *attrselect,
                    limit_clause,
                    f"WITH collect({source_cypher.var}) as nodes, collect(ID({source_cypher.var})) as ids",
                    f"RETURN nodes, [], ids",
                ]
            )
        else:
            cypher = "\n".join(
                [
                    f"MATCH path={source_cypher.pattern}{path_cypher.pattern}{target_cypher.pattern}",
                    *filters,
                    *attrselect,
                    limit_clause,
                    f"WITH apoc.agg.graph({pathvar}) AS subgraph,",
                    f"      COLLECT(DISTINCT ID({source_cypher.var})) AS sources",
                    f"RETURN subgraph.nodes, subgraph.relationships, sources",
                ]
            )
        results = list(self.cypher(cypher))
        if results:
            return (*list(results[0]), cypher)
        return [], [], [], cypher

    def subgraph_query(self):
        pass

    def get_node_attrs(self, node_ids):
        node_ids = [int(i) for i in node_ids]
        ret = defaultdict(dict)
        for node, etymology in self.cypher(
            f"""
            MATCH (n)
            WHERE ID(n) IN {node_ids}
            RETURN ID(n), n.etymology
            """
        ):
            ret[node]["etymology"] = etymology

        for node, labels in self.cypher(
            f"""
            MATCH (n)
            WHERE ID(n) IN {node_ids}
            RETURN ID(n), LABELS(n)
            """
        ):
            ret[node]["labels"] = labels

        for node, pos in self.cypher(
            f"""
            MATCH (n)--(p:POS)
            WHERE ID(n) IN {node_ids}
            RETURN ID(n), p.type
            """
        ):
            ret[node].setdefault("gloss_per_pos", {})[pos] = []

        for node, pos, gloss in self.cypher(
            f"""
            MATCH (n)--(g:Gloss)--(p:POS)
            WHERE ID(n) IN {node_ids} AND (g)--(p)
            RETURN ID(n), p.type, g
            """
        ):
            ret[node]["gloss_per_pos"][pos].append(gloss)

        for node, prs in self.cypher(
            f"""
            MATCH (n)--(pr:Pronunc)
            WHERE ID(n) IN {node_ids}
            RETURN ID(n), collect(pr)
            """
        ):
            ret[node]["pronunciation"] = prs

        return ret

    def get_node_neighbors(self, node_id):
        return list(
            self.cypher(
                f"""
                MATCH (n)--(n2:Word)
                WHERE ID(n) = {node_id}
                RETURN n2"""
            )
        )

    def aggregate(self, labels: List[str], include_languages):
        if not labels and not include_languages:
            return [], 0
        labels = as_cypher_list(labels)
        properties = as_cypher_list(["language"] if include_languages else [])
        return list(
            self.cypher(
                f"""
                CALL apoc.nodes.group({labels}, {properties})
                YIELD node, relationship
                RETURN collect(node), collect(relationship)
                """
            )
        )[0]

    def get_all_languages(self):
        return [
            r["n.language"]
            for r in self.cypher("MATCH (n:EtymologyEntry) RETURN DISTINCT n.language")
        ]

    def get_all_pos(self, cutoff=10):
        return [
            record["t"]
            for record in self.cypher(
                f"""
                MATCH (pos:POS)--(n)
                WITH DISTINCT pos.type AS t, COUNT(n) AS c
                WHERE c >= {cutoff} RETURN t ORDER BY c DESC
                """
            )
        ]

    def get_glosslabels(self, min=10):
        return [
            record["l"]
            for record in self.cypher(
                f"""
                MATCH (n:Gloss) UNWIND n.labels AS l
                WITH l, count(l) AS c WHERE c >= {min}
                RETURN l ORDER BY c DESC
                """
            )
        ]

    def get_node_labels(self):
        return [
            record["l"]
            for record in self.cypher(
                """
                MATCH (n)
                WHERE n:EtymologyEntry OR n:Entity OR n:NAE
                WITH LABELS(n) AS labels UNWIND labels AS l
                RETURN DISTINCT l
                """
            )
        ]

    def create_node_label(self, name: str, selected_ids: List[str]) -> None:
        cypher = "\n".join(
            [
                "MATCH (n)",
                f"WHERE ID(n) IN {[int(i) for i in selected_ids]}",
                f"SET n:{name}",
                "RETURN n",
            ]
        )
        list(self.cypher(cypher))

    def delete_node_labels(self, names: List[str]):
        if not names:
            return
        labels = set(names).difference(PROTECTED_NODE_LABELS)
        for label in labels:
            list(
                self.cypher(
                    f"""
                    MATCH (n:{label})
                    REMOVE n:{label}
                    RETURN n
                    """
                )
            )

    def export_selection(self, node_ids: List[str], relationships: List[str]):
        nodes = list(
            self.cypher(
                "\n".join(
                    [
                        "MATCH (n)",
                        f"WHERE ID(n) in {[int(i) for i in node_ids]}",
                        "OPTIONAL MATCH (n)--(a:Attr)",
                        "RETURN id(n), n, collect(a)",
                    ]
                )
            )
        )
        relationships = list(
            self.cypher(
                "\n".join(
                    [
                        f"MATCH ()-[r]-()",
                        f"WHERE ID(r) in {[int(i) for i in relationships]}",
                        "RETURN collect(r)",
                    ]
                )
            )
        )[0]
        return nodes, relationships


class Neo4jConnector:
    def __init__(self, config: Neo4jConfig):
        self.logger = logging.getLogger("Neo4jConnector")
        self.config = config
        self.driver = neo4j.GraphDatabase.driver(config.uri, auth=config.auth)
        self.driver.verify_connectivity()

    def new_session(self) -> EtymGraphSession:
        return EtymGraphSession(self.driver.session(database=self.config.database))
