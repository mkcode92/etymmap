import logging
import os
from argparse import ArgumentParser

from etymmap.wiktionary.dump2db import (
    db_and_collection_by_filename,
    dump2db,
    EntryConverter,
)
from etymmap.wiktionary.dumps import DumpProcessor
from etymmap.wiktionary.store.mongo import MongoEntryStore

logger = logging.getLogger("dump2mongo")


def make_dumpargparser(parser=ArgumentParser()):
    parser.add_argument("DUMP", type=str, help="Path to a dumpfile")
    parser.add_argument(
        "--ignore-noheading",
        type=bool,
        default=True,
        help="Ignore text outside a section",
    )
    parser.add_argument(
        "--nworkers", type=int, default=None, help="number of parallel converters"
    )
    parser.add_argument(
        "--estimate",
        type=int,
        default=8.16 * 10**6,  # current number of pages
        help="Number of pages expected in the dump, improves progress logging.",
    )
    parser.add_argument(
        "--chunksize",
        type=int,
        default=100,
        help="If set pages will be processed in chunks of this size (MB).",
    )
    return parser


def make_dumpargs(args):
    assert os.path.isfile(args.DUMP)
    return DumpProcessor(args.DUMP), {
        "mp_processes": args.nworkers or 1,
        "progress": {"unit": " pages", "total": args.estimate},
        "chunksize_bytes": args.chunksize * 10**6,
    }


def make_argparser(parser=ArgumentParser()):
    parser = make_dumpargparser(parser)
    parser.add_argument(
        "-a",
        "--address",
        type=str,
        default="mongodb://localhost:27017",
        help="The address of the mongo db",
    )
    parser.add_argument(
        "-t",
        "--target",
        type=str,
        nargs="+",
        default=[],
        help="The mongo target (database, collection). If not specified, it is inferred from the dump name",
    )
    parser.add_argument(
        "-c", "--clear", action="store_true", help="Override existing collection"
    )
    return parser


def main(args):
    db, collection = db_and_collection_by_filename(args.DUMP)
    mongo_config = {
        "address": args.address,
        "dbname": args.target[0] if args.target else db,
        "collection": args.target[1] if len(args.target) == 2 else collection,
        "force_fresh": args.clear,
    }
    mstore = MongoEntryStore.from_config(mongo_config)
    print(f"Connected to {mstore}")
    processor, kwargs = make_dumpargs(args)
    dump2db(
        mstore, processor, converter=EntryConverter(args.ignore_noheading), **kwargs
    )
    print("\nDone.")
