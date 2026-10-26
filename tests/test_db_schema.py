"""JM-1: schema, connect and init_db."""
 
import sqlite3
 
import pytest
 
from service_tracker.db import connect, init_db
 
 
def table_names(conn):
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {row["name"] for row in rows}
 
 
def add_equipment(conn, serial="SW-4410"):
    with conn:
        conn.execute(
            "INSERT INTO equipment (serial_number, equipment_type) VALUES (?, ?)",
            (serial, "switch"),
        )
 
 
def add_visit(conn, serial="SW-4410", visit_date="2026-10-01"):
    with conn:
        conn.execute(
            "INSERT INTO visits (visit_id, serial_number, technician, visit_date,"
            " problem_code, outcome) VALUES (?, ?, ?, ?, ?, ?)",
            ("V-0001", serial, "T-01", visit_date, "PWR", "fixed"),
        )
 
 
def test_init_db_creates_the_four_tables(conn):
    assert {"equipment", "visits", "parts_used", "stock"} <= table_names(conn)
 
 
def test_init_db_sets_schema_version(conn):
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
 
 
def test_connect_turns_foreign_keys_on(conn):
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
 
 
def test_init_db_twice_is_safe_and_keeps_data(conn):
    add_equipment(conn)
    init_db(conn)
    count = conn.execute("SELECT COUNT(*) FROM equipment").fetchone()[0]
    assert count == 1
 
 
def test_connect_uses_service_db_path(tmp_path, monkeypatch):
    db_path = tmp_path / "from_env.db"
    monkeypatch.setenv("SERVICE_DB_PATH", str(db_path))
    conn = connect()
    try:
        init_db(conn)
    finally:
        conn.close()
    assert db_path.exists()
 
 
def test_visit_with_unknown_serial_is_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError):
        add_visit(conn, serial="NOT-SAVED")
 
 
@pytest.mark.parametrize("bad_date", ["2026-13-05", "2026-02-30", "05/10/2026"])
def test_impossible_visit_date_is_rejected(conn, bad_date):
    add_equipment(conn)
    with pytest.raises(sqlite3.IntegrityError):
        add_visit(conn, visit_date=bad_date)
 
 
def test_valid_visit_is_saved(conn):
    add_equipment(conn)
    add_visit(conn)
    row = conn.execute("SELECT visit_date FROM visits").fetchone()
    assert row["visit_date"] == "2026-10-01"
 
 
def test_parts_used_accepts_part_not_in_stock(conn):
    add_equipment(conn)
    add_visit(conn)
    with conn:
        conn.execute(
            "INSERT INTO parts_used (visit_id, part_number, quantity) VALUES (?, ?, ?)",
            ("V-0001", "P-9999", 1),
        )
    count = conn.execute("SELECT COUNT(*) FROM parts_used").fetchone()[0]
    assert count == 1
 