"""Command line for the equipment repair history tracker.

``run`` loads settings, stock, and visits, saves the valid rows, runs the
rules, and prints the report. ``history`` reads visits already stored for
one serial number. This module only connects those pieces. The checks,
the database writes, the rules, and the report text live in their own
modules.

The database path is not chosen here. ``connect()`` uses the ``--db``
argument when one is given, otherwise the ``SERVICE_DB_PATH`` environment
variable, otherwise its own default (``service.db``).
"""

import argparse
import sqlite3
import sys
from contextlib import closing

from service_tracker import __version__
from service_tracker.db import (
    connect,
    history_for_serial,
    init_db,
    load_stock_records,
    save_visits,
)
from service_tracker.loader import (
    InputFileError,
    format_rejections,
    load_stock,
    load_visits,
)
from service_tracker.report import RunSummary, render_report
from service_tracker.rules import run_all_rules
from service_tracker.settings import SettingsError, load_settings


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run one command. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        print(__version__)
        return 0
    if args.command == "run":
        return run_command(args)
    if args.command == "history":
        return history_command(args)
    parser.print_help(sys.stderr)
    return 2


def build_parser():
    """Build the parser for ``run``, ``history``, and ``--version``."""
    parser = argparse.ArgumentParser(
        prog="service-tracker",
        description="Load service visits and print a repair history report.",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="print the package version and exit",
    )
    subcommands = parser.add_subparsers(dest="command")

    run = subcommands.add_parser(
        "run",
        help="load the input files, save visits, and print the report",
    )
    run.add_argument("--visits", required=True, metavar="PATH", help="visit CSV file")
    run.add_argument("--stock", required=True, metavar="PATH", help="stock CSV file")
    run.add_argument(
        "--settings", required=True, metavar="PATH", help="settings JSON file"
    )
    add_db_argument(run)

    history = subcommands.add_parser(
        "history",
        help="show saved visits for one serial number",
    )
    history.add_argument("serial", metavar="SERIAL", help="equipment serial number")
    add_db_argument(history)
    return parser


def add_db_argument(parser):
    """Optional database path. Omitted means ``connect()`` resolves it."""
    parser.add_argument(
        "--db",
        metavar="PATH",
        help="SQLite database file. Overrides SERVICE_DB_PATH.",
    )


def run_command(args) -> int:
    """Load, save, check, and print. Warning flags still return 0."""
    try:
        settings = load_settings(args.settings)
        stock, stock_rej = load_stock(args.stock)
        rows, visit_rej = load_visits(args.visits, settings.part_number_pattern)
    except (SettingsError, InputFileError) as error:
        print(error, file=sys.stderr)
        return 1

    # Stock rejections first, then visit rejections: that is the load order.
    print(format_rejections([*stock_rej, *visit_rej]))

    # None lets connect() apply SERVICE_DB_PATH, then its own default.
    # closing() closes the connection; sqlite's own `with` only commits.
    try:
        with closing(connect(args.db)) as conn:
            init_db(conn)
            load_stock_records(conn, stock)
            result = save_visits(conn, rows)
            flags = run_all_rules(conn, settings)
    except sqlite3.Error as error:
        print(f"database error: {error}", file=sys.stderr)
        return 1

    # One visit can be several CSV rows, one row per part. Count visit ids.
    summary = RunSummary(
        visits_loaded=len({r.visit_id for r in rows}),
        visits_saved=result.saved,
        duplicates=len(result.duplicates),
        rejected=len(stock_rej) + len(visit_rej),
        serials_checked=len({r.serial_number for r in rows}),
    )
    print()
    print(render_report(flags, summary), end="")
    return 0


def history_command(args) -> int:
    """Print saved visits for one serial, oldest first. Does not load CSVs."""
    # Saved serials are stripped and uppercase. Match that form on lookup.
    serial = args.serial.strip().upper()
    try:
        with closing(connect(args.db)) as conn:
            # A new database file has no tables yet. init_db is safe to repeat,
            # so an empty database reports no history instead of raising.
            init_db(conn)
            rows = history_for_serial(conn, serial)
    except sqlite3.Error as error:
        print(f"database error: {error}", file=sys.stderr)
        return 1
    print(format_history(serial, rows))
    return 0


def format_history(serial, rows) -> str:
    """Format ``history_for_serial`` rows. They are already oldest first."""
    if not rows:
        return f"No history for {serial}."
    lines = [f"History for {serial}"]
    for row in rows:
        line = (
            f"{row['visit_id']}  {row['visit_date']}  {row['technician']}  "
            f"{row['problem_code']}  {row['outcome']}"
        )
        if row["part_number"] is not None:
            line += f"  {row['part_number']} x{row['quantity']}"
        lines.append(line)
    return "\n".join(lines)
