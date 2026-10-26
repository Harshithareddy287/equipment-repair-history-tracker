"""Read visit and stock CSVs into models; every bad row becomes a Rejection.

A rejected row is reported with its line number and reason and never
reaches the database. A file that cannot be read at all, or is missing a
column, raises InputFileError instead, since no row in it can be trusted.
"""

import csv
import re
from datetime import date

from service_tracker.models import OUTCOMES, Rejection, ServiceVisit, StockRecord

VISIT_COLUMNS = (
    "visit_id", "serial_number", "equipment_type", "technician", "visit_date",
    "problem_code", "part_number", "quantity_used", "outcome",
)
STOCK_COLUMNS = ("part_number", "description", "quantity_on_hand", "reorder_level")

# date.fromisoformat also takes 20261005 and 2026-W40-1, and int() takes
# "3_000", "+3" and non-ASCII digits, so check the exact shape first.
ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
WHOLE_NUMBER = re.compile(r"-?[0-9]+")


class InputFileError(Exception):
    """A CSV file is missing or lacks a required column."""


class RowError(Exception):
    """One row failed a check; the message is the reason without its line."""


def read_rows(path, columns):
    """Yield (line_number, raw, row) for each data row, with row normalised.

    raw is the row as read. row has every field stripped, serial and part
    numbers uppercased, and short-row gaps as "".
    """
    try:
        f = open(path, encoding="utf-8-sig", newline="")
    except FileNotFoundError:
        raise InputFileError(f"input error: {path} not found") from None
    with f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        for column in columns:
            if column not in header:
                raise InputFileError(f'input error: {path} is missing column "{column}"')
        for raw in reader:
            row = {k: (v or "").strip() for k, v in raw.items() if k is not None}
            for key in ("serial_number", "part_number"):
                if key in row:
                    row[key] = row[key].upper()
            yield reader.line_num, raw, row


def require(row, key):
    if not row[key]:
        raise RowError(f"{key} is missing")
    return row[key]


def whole_number(row, key):
    value = row[key]
    if not WHOLE_NUMBER.fullmatch(value):
        raise RowError(f"{key} is not a whole number ({value})")
    number = int(value)
    if number < 0:
        raise RowError(f"{key} is negative ({value})")
    return number


def parse_visit(row, pattern):
    visit_id = require(row, "visit_id")
    serial_number = require(row, "serial_number")

    value = row["visit_date"]
    try:
        if not ISO_DATE.fullmatch(value):
            raise ValueError
        visit_date = date.fromisoformat(value)
    except ValueError:
        raise RowError(f"visit_date is not an ISO date ({value})") from None

    quantity_used = whole_number(row, "quantity_used")
    if quantity_used == 0:
        raise RowError("quantity_used is zero")

    if row["outcome"] not in OUTCOMES:
        allowed = ", ".join(sorted(OUTCOMES))
        raise RowError(f"outcome is not one of {allowed} ({row['outcome']})")

    part_number = require(row, "part_number")
    if not pattern.fullmatch(part_number):
        raise RowError(f"part_number does not match {pattern.pattern} ({part_number})")

    return ServiceVisit(
        visit_id=visit_id,
        serial_number=serial_number,
        equipment_type=row["equipment_type"],
        technician=row["technician"],
        visit_date=visit_date,
        problem_code=row["problem_code"],
        part_number=part_number,
        quantity_used=quantity_used,
        outcome=row["outcome"],
    )


def load_visits(path, part_number_pattern: str) -> tuple[list[ServiceVisit], list[Rejection]]:
    pattern = re.compile(part_number_pattern)
    visits, rejections = [], []
    for line, raw, row in read_rows(path, VISIT_COLUMNS):
        try:
            visits.append(parse_visit(row, pattern))
        except RowError as e:
            rejections.append(Rejection("visits", line, raw, f"line {line}: {e}"))
    return visits, rejections


def load_stock(path) -> tuple[list[StockRecord], list[Rejection]]:
    records, rejections = [], []
    first_seen = {}  # part_number -> line it was first loaded from
    for line, raw, row in read_rows(path, STOCK_COLUMNS):
        try:
            part_number = require(row, "part_number")
            if part_number in first_seen:
                raise RowError(
                    f"part_number is a duplicate of line {first_seen[part_number]} ({part_number})"
                )
            record = StockRecord(
                part_number=part_number,
                description=row["description"],
                quantity_on_hand=whole_number(row, "quantity_on_hand"),
                reorder_level=whole_number(row, "reorder_level"),
            )
        except RowError as e:
            rejections.append(Rejection("stock", line, raw, f"line {line}: {e}"))
            continue
        first_seen[part_number] = line
        records.append(record)
    return records, rejections


def format_rejections(rejections: list[Rejection]) -> str:
    if not rejections:
        return "No rows rejected."
    noun = "row" if len(rejections) == 1 else "rows"
    return "\n".join([f"{len(rejections)} {noun} rejected:", *(r.reason for r in rejections)])
