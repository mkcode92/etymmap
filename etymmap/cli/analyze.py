from argparse import ArgumentParser

from etymmap.analyze import StatisticsWriter
from etymmap.cli.dump2mongo import make_dumpargparser, make_dumpargs


def make_argparser(parser=ArgumentParser()):
    parser = make_dumpargparser(parser)
    parser.add_argument(
        "-o", "--output-dir", type=str, help="path to the output directory"
    )
    parser.add_argument(
        "--namespaces",
        nargs="+",
        default=[0, 118],
        help="the namespaces to analyze in-depth",
    )
    return parser


def main(args):
    processor, kwargs = make_dumpargs(args)
    StatisticsWriter(parse_namespaces=args.namespaces).write_stats(
        processor, out=args.output_dir, **kwargs
    )
