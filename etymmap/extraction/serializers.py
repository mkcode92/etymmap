import csv
import json
import logging
import re
import urllib.parse
from abc import ABC
from pathlib import Path
from typing import Iterable, Dict, Type

import networkx as nx
import rdflib
from rdflib import URIRef, RDF
from rdflib.term import Literal
from tqdm import tqdm

from etymmap.graph.nodes import *
from etymmap.graph.relations import Relation, RelationAttributes
from etymmap.specific import Specific
from etymmap.wiktionary import Wiktionary


class GraphSerializer(abc.ABC):
    name = ""

    def __init__(self, directory=".", **kwargs):
        self.directory = Path(directory)
        self.logger = logging.getLogger(self.__class__.__name__)

    def resolved_nodes(self, graph, wiktionary, head=0, expand_stubs=True):
        def stub_resolve(stubs: List[SingleMeaningStub]):
            if not stubs:
                return
            filter_ = {
                "$or": [
                    {"$and": [{"title": stub.term}, {"language": stub.language}]}
                    for stub in stubs
                ]
            }
            for entry in wiktionary.entries(filter=filter_):
                yield from Specific.entry_parser.make_lexemes(entry)

        def _nodes():
            if head:
                # if head, yield nodes from head of relations
                seen = set()
                for i, (src, tgt, _) in enumerate(graph.edges):
                    if i >= head:
                        break
                    for node_ in (src, tgt):
                        if node_ not in seen:
                            yield node_
                            seen.add(node_)
            else:
                yield from graph.nodes

        stubs = []
        for node in _nodes():
            if expand_stubs and isinstance(node, SingleMeaningStub):
                stubs.append(node)
                if len(stubs) > 10000:
                    yield from stub_resolve(stubs)
                    stubs.clear()
            else:
                yield node
        yield from stub_resolve(stubs)

    def serialize(
        self,
        graph: nx.MultiDiGraph,
        wiktionary: Wiktionary,
        progress=True,
        head=0,
        expand_stubs=True,
    ):
        def relations():
            for i, (source, target, attrs) in enumerate(graph.edges(data=True)):
                if head and i >= head:
                    break
                yield Relation(source, target, RelationAttributes(**attrs))

        with self as serializer:
            nodes = self.resolved_nodes(graph, wiktionary, head, expand_stubs)
            if progress:
                nodes = tqdm(
                    nodes,
                    total=head if head else graph.number_of_nodes(),
                    unit=" nodes",
                )
            self.logger.debug("Writing nodes")
            serializer.write_nodes(nodes)
            relations = (
                tqdm(relations(), total=graph.number_of_edges(), unit=" edges")
                if progress
                else relations()
            )
            self.logger.debug("Writing relations")
            serializer.write_relations(relations)

    @classmethod
    def get_by_name(cls, name):
        stack: List[Type[GraphSerializer]] = [cls]
        while stack:
            c = stack.pop()
            if c.name == name:
                return c
            stack.extend(c.__subclasses__())
        raise ValueError(f"Found no serializer for {name}")

    @classmethod
    def list_names(cls):
        return [subclass.name for subclass in cls.__subclasses__()]

    def __enter__(self) -> "GraphSerializer":
        pass

    def __exit__(self, *args, **kwargs):
        pass

    @abc.abstractmethod
    def write_nodes(self, nodes: Iterable[Node]) -> None:
        pass

    @abc.abstractmethod
    def write_relations(self, relations: Iterable[Relation]) -> None:
        pass


class LemonSerializer(GraphSerializer):
    name = "lemon"

    default_urls = {
        "lime": "https://raw.githubusercontent.com/ontolex/ontolex/master/Ontologies/w3c/ttl/lime.ttl",
        "ontolex": "https://raw.githubusercontent.com/ontolex/ontolex/master/Ontologies/w3c/ttl/ontolex.ttl",
        "lemonety": "https://raw.githubusercontent.com/anasfkhan81/lemonEty/master/lemonEty.ttl",
        "lexinfo": "https://raw.githubusercontent.com/ontolex/lexinfo/master/ontology/3.0/lexinfo.owl",
    }

    def __init__(
        self, directory=".", baseurl=r"http://etymmap.org/graph#", **writer_kwargs
    ):
        super().__init__(directory)
        self.baseurl = baseurl
        self.logger = logging.getLogger("LemonSerializer")
        self.file = Path(self.directory) / "etymmap.ttl"
        self.graph = rdflib.Graph()
        self.graph.bind("etymmap", baseurl)
        for ontology in self.default_urls.values():
            self.graph.parse(
                ontology, format="xml" if ontology.endswith("owl") else "turtle"
            )
        self.ns = self.make_ns_map()
        self.lexicon = self.create_lexicon()

    def make_ns_map(self):
        ns = {k: ns for k, ns in self.graph.namespaces()}
        # use lexinfo 3.0
        ns["lexinfo"] = ns["default1"]
        # this is not extracted correctly
        ns["lime"] = ns[""]
        # make lemonety explicit
        ns["lemonety"] = ns["default2"]
        return ns

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        self.graph.serialize(self.file, format="turtle", encoding="utf-8")

    def create_lexicon(self):
        lexicon = self.uri("", "etymmap")
        self.graph.add((self.uri("", "etymmap"), RDF.type, self.uri("lexicon", "lime")))
        return lexicon

    def uri(self, element, ns_id):
        return URIRef(f"{self.ns[ns_id]}{element}")

    def noderepr(self, node: Node) -> str:
        def clean(string: str):
            return urllib.parse.quote(re.sub(r"\s+", "_", string))

        if isinstance(node, LexemeBase):
            term = clean(node.term)
            language = clean(node.language)
            return f"{self.baseurl}{term}_{language}_{node.sense_idx}"
        elif isinstance(node, Phantom):
            return f"{self.baseurl}_phantom_{node.id}"
        elif isinstance(node, Entity):
            return f"{self.baseurl}{clean(node.id)}"

    def write_nodes(self, nodes: Iterable[Node]):
        uri = self.uri
        IS_A = uri("type", "rdf")
        ETYMON = uri("Etymon", "lemonety")
        HAS_ENTRY = uri("entry", "lime")
        HAS_LANGUAGE = uri("language", "dct")
        HAS_FORM = uri("canonicalForm", "ontolex")
        HAS_REPR = uri("writtenRep", "ontolex")
        HAS_PHONETIC_REPR = uri("phoneticRep", "ontolex")
        SENSE = uri("LexicalSense", "ontolex")
        HAS_SENSE = uri("sense", "ontolex")
        HAS_DEFINTION = uri("definition", "ontolex")
        HAS_POS = uri("partOfSpeech", "lexinfo")

        add = self.graph.add
        for node in nodes:
            self.logger.debug(f"Write {node}")
            node_repr = self.noderepr(node)
            entry = URIRef(node_repr)
            form = URIRef(node_repr + "_F")
            if isinstance(node, LexemeBase):
                add((self.lexicon, HAS_ENTRY, entry))
                add((entry, IS_A, ETYMON))
                add((entry, HAS_LANGUAGE, Literal(node.language)))
                add((entry, HAS_FORM, form))
                add((form, HAS_REPR, Literal(node.term)))
                pos = set()
                for i, gloss in enumerate(getattr(node, "glosses") or []):
                    sense = URIRef(f"{node_repr}_S{i}")
                    add((sense, IS_A, SENSE))
                    add((entry, HAS_SENSE, sense))
                    add((sense, HAS_DEFINTION, Literal(gloss.text)))
                    pos.add(Literal(gloss.pos or "?"))
                for p in pos:
                    add((entry, HAS_POS, Literal(p)))

                if isinstance(node, EntryLexeme):
                    if node.pronunciation:
                        ipas = []
                        self.logger.debug(node.pronunciation)
                        for pron in node.pronunciation:
                            ipa = pron.ipa
                            if isinstance(ipa, str):
                                ipas.append(ipa)
                            else:
                                ipas.extend(ipa)
                        self.logger.debug(ipas)
                        for ipa in ipas:
                            add((form, HAS_PHONETIC_REPR, Literal(ipa)))

    def write_relations(self, relations: Iterable[Relation]):
        uri = self.uri
        add = self.graph.add
        IS_A = uri("type", "rdf")
        ETYLINK = uri("EtyLink", "lemonety")
        HAS_TYPE = uri("etyLinkType", "lemonety")
        HAS_SOURCE = uri("etySource", "lemonety")
        HAS_TARGET = uri("etyTarget", "lemonety")
        for relation in relations:
            src, tgt, type = relation.src, relation.tgt, relation.attrs.type
            uri = self.uri(f"rel_{hash((src, tgt, type))}", "etymmap")
            add((uri, IS_A, ETYLINK))
            add((uri, HAS_SOURCE, URIRef(self.noderepr(src))))
            add((uri, HAS_TARGET, URIRef(self.noderepr(tgt))))
            add((uri, HAS_TYPE, Literal(type)))


class TableContext:
    logger = logging.getLogger("TableContext")

    def __init__(self, name: str, header: List[str]):
        self.name = name
        self.header = header
        self.file = None
        self.writer = None

    def enter(self, directory, **csv_kwargs):
        filename = directory / f"{self.name}.csv"
        self.logger.info(f"Writing to file {filename.absolute()}")
        self.file = fh = open(filename, "w", newline="")
        self.writer = writer = csv.writer(
            fh, quoting=csv.QUOTE_NONNUMERIC, **csv_kwargs
        )
        writer.writerow(self.header)

    def close(self):
        self.file.close()


class CSVSerializer(GraphSerializer, ABC):
    def __init__(
        self, directory, tables: Dict[str, TableContext] = None, **writer_kwargs
    ):
        super().__init__(directory, **writer_kwargs)
        self.tables = tables or {}
        self.writer_kwargs = writer_kwargs

    def __enter__(self):
        for table in self.tables.values():
            table.enter(self.directory, **self.writer_kwargs)
        return self

    def __exit__(self, *args, **kwargs):
        for table in self.tables.values():
            table.close()


class SimpleSerializer(CSVSerializer):
    name = "simple"

    def __init__(self, directory=".", **writer_kwargs):
        super().__init__(
            directory,
            {
                ctx.name: ctx
                for ctx in [
                    TableContext(
                        "etymology_entry", ["id", "term", "language", "sense_idx"]
                    ),
                    TableContext("entity", ["id", "name"]),
                    TableContext("etymology", ["type", "src", "tgt"]),
                ]
            },
            **writer_kwargs,
        )

    def serialize(
        self,
        graph: nx.MultiDiGraph,
        wiktionary: Wiktionary,
        progress=True,
        head=0,
        expand_stubs=True,
    ):
        # it is not necessary to expand stubs for this serializer
        super().serialize(graph, wiktionary, progress, head, False)

    def write_nodes(self, nodes: Iterable[Node]):
        entries_writer = self.tables["etymology_entry"].writer
        entity_writer = self.tables["entity"].writer
        for node in nodes:
            if isinstance(node, LexemeBase):
                entries_writer.writerow(
                    [id(node), node.term, node.language, node.sense_idx]
                )
            elif isinstance(node, Entity):
                entity_writer.writerow([id(node), node.name])
            else:
                raise ValueError()

    def write_relations(self, relations: Iterable[Relation]):
        relation_file = self.tables["etymology"].writer
        for relation in relations:
            relation_file.writerow(
                [relation.attrs.type.name, id(relation.src), id(relation.tgt)]
            )


class Neo4jSerializer(CSVSerializer):
    name = "neo4j"

    def __init__(self, directory=".", array_delimiter="@", **csv_kwargs):
        super().__init__(
            directory,
            {
                ctx.name: ctx
                for ctx in [
                    TableContext(
                        "etymology_entry",
                        [
                            "id:ID",
                            "multiword:LABEL",
                            "has_entry:LABEL",
                            "term:string",
                            "language:string",
                            "sense_idx:int",
                            "etymology:string",
                            "etymid:string",
                        ],
                    ),
                    TableContext(
                        "entity",
                        [
                            "id:ID",
                            "name",
                            "occ",
                            "nat",
                            "born",
                            "died",
                            "wikipedia",
                        ],
                    ),
                    TableContext("nae", ["id:ID"]),
                    TableContext("pos", ["id:ID", "type:string"]),
                    TableContext("has_pos", ["node:START_ID", "pos:END_ID"]),
                    TableContext("gloss", ["id:ID", "text:string", "labels:string[]"]),
                    TableContext("has_gloss", ["node:START_ID", "gloss:END_ID"]),
                    TableContext(
                        "pronunciation",
                        ["id:ID", "ipa:string", "accent:string", "kind:string"],
                    ),
                    TableContext(
                        "has_pronunciation", ["node:START_ID", "pronunciation:END_ID"]
                    ),
                    TableContext(
                        "etymology",
                        [
                            "source:START_ID",
                            "target:END_ID",
                            "type:TYPE",
                            "text:string",
                            "uncertain:boolean",
                        ],
                    ),
                ]
            },
            **csv_kwargs,
        )
        self.array_delimiter = array_delimiter
        self.global_pos = set()

    def __exit__(self, *args, **kwargs):
        pos_writer = self.tables["pos"].writer
        for pos_id, pos in self.global_pos:
            pos_writer.writerow([pos_id, pos])
        super().__exit__(*args, **kwargs)

    def is_multiword(self, term: str):
        return " " in term

    def write_nodes(self, nodes: Iterable[Node]):
        for node in nodes:
            if isinstance(node, LexemeBase):
                self.write_etymology_entry(node)
            elif isinstance(node, Entity):
                self.write_entity(node)
            elif isinstance(node, Phantom):
                self.write_nae(node)
            else:
                raise ValueError(f"Unexpected type: {type(node)}")

    def write_relations(self, relations: Iterable[Relation]):
        writer = self.tables["etymology"].writer
        for relation in relations:
            attrs = relation.attrs
            writer.writerow(
                [
                    hash(relation.src.id),
                    hash(relation.tgt.id),
                    attrs.type.name,
                    replace_newline_by_br(attrs.text),
                    attrs.uncertain,
                ]
            )

    def write_etymology_entry(self, node: LexemeBase):
        node_id = hash(node.id)
        if isinstance(node, EntryLexeme):
            has_entry = True
            etymology = replace_newline_by_br(node.etymology)
            etymid = node.etymid or ""
            self.write_pronunciation(node.pronunciation, node_id)
        elif isinstance(node, NoEntryLexeme):
            has_entry = False
            etymology = ""
            etymid = ""
        else:
            raise ValueError(f"Unexpected type: {type(node)}")
        self.tables["etymology_entry"].writer.writerow(
            [
                hash(node.id),
                "Multiword" if self.is_multiword(node.term) else "",
                "Wiktionary" if has_entry else "",
                node.term,
                node.language,
                node.sense_idx,
                replace_newline_by_br(etymology),
                etymid,
            ]
        )
        self.write_glosses(node.glosses, node_id)

    def write_pronunciation(self, pronunciation: List[Pronunciation], node_id: int):
        node_writer = self.tables["pronunciation"].writer
        relation_writer = self.tables["has_pronunciation"].writer
        if pronunciation:
            for i, pron in enumerate(pronunciation):
                ipa = pron.ipa
                kind = pron.kind
                if not isinstance(ipa, list):
                    ipa, kind = [ipa], [kind]
                for j, (ip, ki) in enumerate(zip(ipa, kind)):
                    # this is necessary to get a unique hash
                    pid = hash((i, j, node_id, ip, pron.accent, ki.name))
                    # id, ipa, accent, kind
                    node_writer.writerow([pid, ip, pron.accent, ki.name])
                    relation_writer.writerow([node_id, pid])

    def write_glosses(self, glosses: List[Gloss], node_id: int):
        gloss_writer = self.tables["gloss"].writer
        has_gloss_writer = self.tables["has_gloss"].writer
        has_pos_writer = self.tables["has_pos"].writer
        if glosses:
            pos = set()
            for i, gloss in enumerate(glosses):
                gloss_id = hash((node_id, gloss.text, i))
                p = gloss.pos
                if p:
                    pos_id = hash(p)
                    if pos_id not in pos:
                        pos.add(pos_id)
                        has_pos_writer.writerow([node_id, pos_id])
                        self.global_pos.add((pos_id, p))
                    has_pos_writer.writerow([gloss_id, pos_id])
                gloss_writer.writerow(
                    [
                        gloss_id,
                        replace_newline_by_br(gloss.text),
                        self.array_delimiter.join(gloss.labels or []),
                    ]
                )
                has_gloss_writer.writerow([node_id, gloss_id])

    def write_entity(self, node: Entity):
        self.tables["entity"].writer.writerow(
            [
                hash(node.id),
                node.name,
                node.occ,
                node.nat,
                node.born,
                node.died,
                node.wplink,
            ]
        )

    def write_nae(self, node: Phantom):
        self.tables["nae"].writer.writerow([hash(node.id)])


class JSONSerializer(GraphSerializer):
    name = "jsonl"

    def __init__(self, directory=".", **dumps_kwargs):
        super().__init__(directory)
        self.nodes = None
        self.relations = None
        self.dumps_kwargs = dumps_kwargs
        self.nodes_empty = True
        self.relations_empty = True

    def __enter__(self):
        self.nodes = open(self.directory / "nodes.jsonl", "w")
        self.relations = open(self.directory / "relations.jsonl", "w")
        return self

    def __exit__(self, *args, **kwargs):
        for file_ in self.nodes, self.relations:
            if file_:
                file_.close()

    def write_nodes(self, nodes: Iterable[Node]):
        for node in nodes:
            self.nodes.write(
                json.dumps(node.to_dict(), **self.dumps_kwargs).replace("\n", "<br/>")
            )
            self.nodes.write("\n")

    def write_relations(self, relations: Iterable[Relation]):
        for relation in relations:
            self.relations.write(
                json.dumps(relation.to_dict(), **self.dumps_kwargs).replace(
                    "\n", "<br/>"
                )
            )
            self.relations.write("\n")


def replace_newline_by_br(text: str, _newline=re.compile("\n+")):
    if text:
        return _newline.sub("<br/>", text)
    return ""
