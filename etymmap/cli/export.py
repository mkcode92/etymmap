import json
import os
from argparse import ArgumentParser
from pathlib import Path
import networkx as nx

from etymmap.extraction import init_and_configure
from etymmap.extraction.serializers import GraphSerializer
from etymmap.extraction.state import NoFuzzyGlossMatcher
from etymmap.wiktionary import Wiktionary, MongoEntryStore


def make_argparser(parser=ArgumentParser()):
    parser.add_argument(
        "--db-config",
        nargs=3,
        type=str,
        help="Specify the preprocessed wiktionary as ADDRESS DATABASE COLLECTION",
    )
    parser.add_argument(
        "--additional-db-config",
        type=str,
        default="{}",
        help="Other pymongo.MongoClient parameters specified as json",
    )
    parser.add_argument(
        "graph",
        type=str,
        help="Path to a graph (.gpickle)",
    )
    parser.add_argument(
        "--cache", default=".lexicon.pickle", help="File to a cached lexicon"
    )
    parser.add_argument(
        "-f",
        "--format",
        type=str,
        choices=["simple", "json", "lemon", "neo4j"],
        default="neo4j",
    )
    parser.add_argument("-o", "--output-dir", help="The output directory.")
    return parser


def main(args):
    outfile = Path(args.output_dir)
    # make sure we don't fail at writing the results
    assert os.access(outfile.parent, os.W_OK)
    # instantiate the wiktionary (cache)
    mongo_config = {
        k: v for k, v in zip(["address", "dbname", "collection"], args.db_config)
    }
    mongo_config.update(json.loads(args.additional_db_config))
    enw = Wiktionary(
        MongoEntryStore.from_config(mongo_config), default_namespaces=(0, 118)
    )
    init_and_configure(enw, gloss_matcher=NoFuzzyGlossMatcher(), cache=args.cache)
    graph = nx.read_gpickle(args.graph)
    serializer = GraphSerializer.with_name(args.format)(outfile)
    serializer.serialize(graph, enw)


if __name__ == "__main__":
    main(make_argparser().parse_args())
