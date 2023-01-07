import json
import os
from argparse import ArgumentParser
from pathlib import Path

from etymmap.extraction.extractor import SectionExtractor


def collect_all_subclasses(clazz):
    ret = [clazz]
    for clazz in ret:
        for subclass in clazz.__subclasses__():
            ret.append(subclass)
    return ret


extractors = collect_all_subclasses(SectionExtractor)


def make_argparser(parser=ArgumentParser()):
    parser.add_argument(
        "-d",
        "--dump",
        type=str,
        default=None,
        help="A (en-)wiktionary dump. Not required when already parsed into db using the dump2mongo command.",
    )
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
        "--output-dir",
        default=".",
        type=str,
        help="Target directory for the generated files",
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
        help="Only use section extractors for these sections",
    )
    parser.add_argument(
        "--head",
        type=int,
        default=0,
        help="Stop extraction after <head> sections",
    )

    return parser


def main(args):
    output_dir = Path(args.output_dir)
    # make sure we don't fail at writing the results
    assert os.access(output_dir, os.W_OK)
    # instantiate the wiktionary (cache)
    mongo_config = {
        k: v for k, v in zip(["address", "dbname", "collection"], args.db_config)
    }
    mongo_config.update(json.loads(args.additional_db_configs))
    # collect all the section extractors (by class attribute 'name')


if __name__ == "__main__":
    main(make_argparser().parse_args())
