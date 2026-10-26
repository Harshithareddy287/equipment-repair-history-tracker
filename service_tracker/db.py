"""SQLite storage: schema, connections and writes for the service tracker."""
 
import os
import sqlite3
 
DEFAULT_DB_PATH = "service.db"
 
# Dates are ISO text so they sort correctly. CHECK (date(x) IS x) rejects
# impossible dates such as 2026-13-05; with = a NULL from date() would pass.
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
  visit_date    TEXT NOT NULL CHECK (date(visit_date) IS visit_date),
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

 