"""SQLite storage: schema, connections and writes for the service tracker."""

import os
import sqlite3
from dataclasses import dataclass, field

DEFAULT_DB_PATH = "service.db"

# Dates are ISO text so they sort correctly. CHECK (date(x, '+0 days') IS x)
# rejects impossible dates such as 2026-13-05 and 2026-02-30: the '+0 days'
# makes every SQLite version roll 2026-02-30 over to 2026-03-02, which then
# does not match. With = instead of IS, a NULL from date() would pass.
# parts_used.part_number has no foreign key to stock so 1.1.0 can flag
# unknown parts, and quantity_on_hand may go negative so a shortfall shows.
SCHEMA = """
CREATE TABLE IF NOT EXISTS equipment (
  serial_number  TEXT PRIMARY KEY,
  equipment_type TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS visits (
  visit_id      TEXT PRIMARY KEY,
  serial_number TEXT NOT NULL REFERENCES equipment(serial_number),
  technician    TEXT NOT NULL,
  visit_date    TEXT NOT NULL CHECK (date(visit_date, '+0 days') IS visit_date),
  problem_code  TEXT NOT NULL,
  outcome       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS parts_used (
  id          INTEGER PRIMARY KEY,
  visit_id    TEXT NOT NULL REFERENCES visits(visit_id),
  part_number TEXT NOT NULL,
  quantity    INTEGER NOT NULL CHECK (quantity > 0)
);
CREATE TABLE IF NOT EXISTS stock (
  part_number      TEXT PRIMARY KEY,
  description      TEXT NOT NULL,
  quantity_on_hand INTEGER NOT NULL,
  reorder_level    INTEGER NOT NULL CHECK (reorder_level >= 0)
);
CREATE INDEX IF NOT EXISTS idx_visits_serial_date ON visits(serial_number, visit_date);
PRAGMA user_version = 1;
"""


def connect(path=None) -> sqlite3.Connection:
    """Open the database with foreign keys on.

    The path comes from the argument, then SERVICE_DB_PATH, then
    service.db. Close it with contextlib.closing(connect()): `with conn:`
    commits or rolls back but does not close.
    """
    path = path or os.environ.get("SERVICE_DB_PATH", DEFAULT_DB_PATH)
    conn = sqlite3.connect(path)
    # SQLite turns foreign keys off for every new connection by default.
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn) -> None:
    """Create the tables and index. Safe to run on an existing database."""
    conn.executescript(SCHEMA)


def load_stock_records(conn, records) -> None:
    """Insert or update stock parts from the loader, in one transaction.

    A new part is inserted with its quantity from the file. An existing part
    gets its description and reorder level updated, but keeps its
    quantity_on_hand: saved visits have already taken stock off it, so
    re-running the same files must not put that stock back.
    """
    with conn:
        conn.executemany(
            """
            INSERT INTO stock (part_number, description, quantity_on_hand, reorder_level)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(part_number) DO UPDATE SET
              description = excluded.description,
              reorder_level = excluded.reorder_level
            """,
            [
                (r.part_number, r.description, r.quantity_on_hand, r.reorder_level)
                for r in records
            ],
        )


# These fields must be the same on every row of one visit.
VISIT_FIELDS = (
    "visit_id",
    "serial_number",
    "equipment_type",
    "technician",
    "visit_date",
    "problem_code",
    "outcome",
)


@dataclass
class SaveResult:
    """What save_visits did with a batch."""

    saved: int = 0
    duplicates: list[str] = field(default_factory=list)  # visit_ids already saved
    failed: list[tuple[str, str]] = field(default_factory=list)  # (visit_id, reason)


def save_visit(conn, rows) -> None:
    """Save one visit, its parts used and the stock change in one transaction.

    rows are the ServiceVisit rows of one visit, one row per part. If any
    write fails, `with conn:` rolls back every write, so no half-saved visit
    and no wrong stock count is left behind. Stock may go negative, and a
    part that is not in stock updates no rows.
    """
    if not rows:
        raise ValueError("a visit needs at least one row")
    first = rows[0]
    for name in VISIT_FIELDS:
        if any(getattr(r, name) != getattr(first, name) for r in rows):
            raise ValueError(f"visit {first.visit_id}: rows disagree on {name}")

    with conn:
        conn.execute(
            "INSERT INTO equipment (serial_number, equipment_type) VALUES (?, ?)"
            " ON CONFLICT(serial_number) DO NOTHING",
            (first.serial_number, first.equipment_type),
        )
        conn.execute(
            "INSERT INTO visits (visit_id, serial_number, technician, visit_date,"
            " problem_code, outcome) VALUES (?, ?, ?, ?, ?, ?)",
            (
                first.visit_id,
                first.serial_number,
                first.technician,
                first.visit_date.isoformat(),
                first.problem_code,
                first.outcome,
            ),
        )
        for r in rows:
            conn.execute(
                "INSERT INTO parts_used (visit_id, part_number, quantity) VALUES (?, ?, ?)",
                (r.visit_id, r.part_number, r.quantity_used),
            )
            conn.execute(
                "UPDATE stock SET quantity_on_hand = quantity_on_hand - ?"
                " WHERE part_number = ?",
                (r.quantity_used, r.part_number),
            )


def save_visits(conn, rows) -> SaveResult:
    """Save a batch of rows, one transaction per visit.

    A visit already in the database is skipped and reported as a duplicate,
    so re-running the same files changes nothing. A visit that fails is
    reported and the rest of the batch is still saved.
    """
    groups = {}  # visit_id -> rows; a dict keeps the file order
    for r in rows:
        groups.setdefault(r.visit_id, []).append(r)

    result = SaveResult()
    for visit_id, visit_rows in groups.items():
        exists = conn.execute(
            "SELECT 1 FROM visits WHERE visit_id = ?", (visit_id,)
        ).fetchone()
        if exists:
            result.duplicates.append(visit_id)
            continue
        try:
            save_visit(conn, visit_rows)
        except (sqlite3.Error, ValueError) as error:
            result.failed.append((visit_id, str(error)))
        else:
            result.saved += 1
    return result
