"""JM-3: read-only queries. Rows are inserted with SQL, not save_visit."""

from service_tracker.db import (
    all_visits,
    history_for_serial,
    low_stock_parts,
    unknown_parts,
)


def add_equipment(conn, serial):
    with conn:
        conn.execute(
            "INSERT INTO equipment (serial_number, equipment_type) VALUES (?, ?)",
            (serial, "switch"),
        )


def add_visit(conn, visit_id, serial, visit_date, outcome="fixed"):
    with conn:
        conn.execute(
            "INSERT INTO visits (visit_id, serial_number, technician, visit_date,"
            " problem_code, outcome) VALUES (?, ?, ?, ?, ?, ?)",
            (visit_id, serial, "T-01", visit_date, "PWR", outcome),
        )


def add_part(conn, visit_id, part_number, quantity=1):
    with conn:
        conn.execute(
            "INSERT INTO parts_used (visit_id, part_number, quantity) VALUES (?, ?, ?)",
            (visit_id, part_number, quantity),
        )


def add_stock(conn, part_number, on_hand, reorder_level):
    with conn:
        conn.execute(
            "INSERT INTO stock (part_number, description, quantity_on_hand, reorder_level)"
            " VALUES (?, ?, ?, ?)",
            (part_number, f"Part {part_number}", on_hand, reorder_level),
        )


def test_history_is_only_that_serial_oldest_first(conn):
    add_equipment(conn, "SW-4410")
    add_equipment(conn, "RT-2001")
    # Inserted out of order on purpose.
    add_visit(conn, "V-0003", "SW-4410", "2026-10-20")
    add_visit(conn, "V-0001", "SW-4410", "2026-10-01")
    add_visit(conn, "V-0002", "RT-2001", "2026-10-05")
    add_part(conn, "V-0003", "P-1001")
    add_part(conn, "V-0001", "P-1002", 2)

    history = history_for_serial(conn, "SW-4410")

    assert [h["visit_id"] for h in history] == ["V-0001", "V-0003"]
    assert history[0] == {
        "visit_id": "V-0001",
        "visit_date": "2026-10-01",
        "technician": "T-01",
        "problem_code": "PWR",
        "outcome": "fixed",
        "part_number": "P-1002",
        "quantity": 2,
    }


def test_history_includes_a_visit_with_no_parts(conn):
    add_equipment(conn, "SW-4410")
    add_visit(conn, "V-0001", "SW-4410", "2026-10-01")

    history = history_for_serial(conn, "SW-4410")

    assert len(history) == 1
    assert history[0]["part_number"] is None
    assert history[0]["quantity"] is None


def test_history_for_unknown_serial_is_empty(conn):
    assert history_for_serial(conn, "NO-SUCH-SERIAL") == []


def test_all_visits_ordered_by_serial_then_date(conn):
    add_equipment(conn, "SW-4410")
    add_equipment(conn, "RT-2001")
    add_visit(conn, "V-0001", "SW-4410", "2026-10-09")
    add_visit(conn, "V-0002", "RT-2001", "2026-10-05")
    add_visit(conn, "V-0003", "SW-4410", "2026-10-01")

    visits = all_visits(conn)

    assert [(v["serial_number"], v["visit_date"]) for v in visits] == [
        ("RT-2001", "2026-10-05"),
        ("SW-4410", "2026-10-01"),
        ("SW-4410", "2026-10-09"),
    ]
    assert set(visits[0]) == {"visit_id", "serial_number", "visit_date", "outcome"}


def test_low_stock_includes_equal_and_negative_but_not_above(conn):
    add_stock(conn, "P-1001", 5, 5)   # equal to reorder level: low
    add_stock(conn, "P-1002", -2, 3)  # shortfall: low
    add_stock(conn, "P-1003", 6, 5)   # above: not low

    low = low_stock_parts(conn)

    assert [p["part_number"] for p in low] == ["P-1001", "P-1002"]
    assert low[1]["quantity_on_hand"] == -2


def test_unknown_parts_returns_part_missing_from_stock(conn):
    add_stock(conn, "P-1001", 10, 3)
    add_equipment(conn, "SW-4410")
    add_visit(conn, "V-0001", "SW-4410", "2026-10-01")
    add_part(conn, "V-0001", "P-1001")
    add_part(conn, "V-0001", "P-9999", 2)

    assert unknown_parts(conn) == [{
        "visit_id": "V-0001",
        "serial_number": "SW-4410",
        "visit_date": "2026-10-01",
        "part_number": "P-9999",
        "quantity": 2,
    }]


def test_unknown_parts_empty_when_all_parts_known(conn):
    add_stock(conn, "P-1001", 10, 3)
    add_equipment(conn, "SW-4410")
    add_visit(conn, "V-0001", "SW-4410", "2026-10-01")
    add_part(conn, "V-0001", "P-1001")

    assert unknown_parts(conn) == []


def test_version_1_database_with_unknown_parts_is_read_by_every_query(conn):
    # Rolling back from 1.1.0 to 1.0.0 is safe because the schema is the same:
    # a version 1 database that holds unknown-part rows still reads cleanly.
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    add_stock(conn, "P-1001", 1, 3)
    add_equipment(conn, "SW-4410")
    add_visit(conn, "V-0001", "SW-4410", "2026-10-01")
    add_part(conn, "V-0001", "P-1001")
    add_part(conn, "V-0001", "P-9999")

    assert len(history_for_serial(conn, "SW-4410")) == 2
    assert len(all_visits(conn)) == 1
    assert len(low_stock_parts(conn)) == 1
    assert len(unknown_parts(conn)) == 1
