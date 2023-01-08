import json
import os
from argparse import ArgumentParser
from pathlib import Path
import networkx as nx

from etymmap.extraction import init_and_configure
from etymmap.extraction.extractor import SectionExtractor, EtymologyExtractor
from etymmap.extraction.state import NoFuzzyGlossMatcher
from etymmap.graph import ReducedRelations
from etymmap.specific_en.languages import load_phylogenetic_tree
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
        "-o",
        "--output",
        default="./graph.gpickle",
        type=str,
        help="Where to store the graph",
    )
    parser.add_argument(
        "--ns",
        "--namespaces",
        type=int,
        nargs="+",
        default=[0, 118],
        help="The namespaces targeted by the extraction",
    )
    parser.add_argument(
        "-s",
        "--sections",
        type=str,
        nargs="+",
        default=["Etymology", "Descendants"],
        choices=["Etymology", "Descendants", "RelatedTerms", "DerivedTerms"],
        help="Only use section extractors for these sections",
    )
    parser.add_argument(
        "--head",
        type=int,
        default=0,
        help="Stop extraction after <head> sections",
    )
    parser.add_argument(
        "--reduction",
        choices=["transitive", "full", "off"],
        default="full",
        help="Apply transitive and/or specificity reduction to the graph",
    )
    parser.add_argument(
        "--cache", default=".lexicon.pickle", help="File to cache the lexicon"
    )
    return parser


def main(args):
    outfile = Path(args.output)
    # make sure we don't fail at writing the results
    assert os.access(outfile.parent, os.W_OK)
    # instantiate the wiktionary (cache)
    mongo_config = {
        k: v for k, v in zip(["address", "dbname", "collection"], args.db_config)
    }
    mongo_config.update(json.loads(args.additional_db_config))
    enw = Wiktionary(
        MongoEntryStore.from_config(mongo_config), default_namespaces=args.namespaces
    )
    init_and_configure(enw, gloss_matcher=NoFuzzyGlossMatcher(), cache=args.cache)
    # collect all the section extractors (by class attribute 'name')
    extractor = EtymologyExtractor(
        *[SectionExtractor.with_name(name) for name in args.sections],
        relation_store=ReducedRelations(language_tree=load_phylogenetic_tree())
    )
    extractor.collect_relations(True, head=args.head)
    reduction_flags = (
        [True, True]
        if args.reduction == "full"
        else [True, False]
        if args.reduction == "transitive"
        else [False, False]
    )
    graph = extractor.get_graph(*reduction_flags)
    nx.write_gpickle(graph, outfile)


if __name__ == "__main__":
    main(make_argparser().parse_args())
