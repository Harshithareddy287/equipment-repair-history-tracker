"""Command line entry point.

This scaffold accepts ``--version`` only. Shreyaa owns this module after
the scaffold lands.
"""

import argparse

from service_tracker import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="service-tracker")
    parser.add_argument(
        "--version",
        action="store_true",
        help="print the package version and exit",
    )
    args = parser.parse_args(argv)
    if args.version:
        print(__version__)
    return 0
