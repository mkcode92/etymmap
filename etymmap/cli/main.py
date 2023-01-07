import argparse
import logging
from importlib import import_module

from etymmap.cli import dump2mongo, analyze  # , extract, graph2neo

SUBPARSERS = [dump2mongo, analyze]  # , extract, graph2neo]

logger = logging.getLogger("cli")


def make_argparser():
    main_parser = argparse.ArgumentParser()
    main_parser.add_argument(
        "-l", "--log-level", default=logging.WARNING, help="Set logger level"
    )
    main_parser.add_argument(
        "-s",
        "--specific",
        default="etymmap.specific_en",
        help="The language specific module to use."
        "Must implement a configure() method that calls"
        "etymmap.specific.configure() with appropriate"
        "parameters.",
    )
    subparsers = main_parser.add_subparsers(dest="command")
    for module in SUBPARSERS:
        parser = subparsers.add_parser(module.__name__.split(".")[-1])
        module.make_argparser(parser)
    return main_parser


def log_level(level):
    try:
        return int(level)
    except ValueError:
        return str(level).upper()


def main():
    parser = make_argparser()
    args = parser.parse_args()
    logging.basicConfig(level=log_level(args.log_level))
    logger.debug(args)
    specific = import_module(args.specific)
    specific.configure()
    if not args.command:
        parser.print_help()
    else:
        getattr(globals()[args.command], "main")(args)


if __name__ == "__main__":
    main()
