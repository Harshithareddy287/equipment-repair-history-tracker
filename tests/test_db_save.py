"""JM-2: save_visit and save_visits."""

import sqlite3
from dataclasses import replace
from datetime import date

import pytest

from service_tracker.db import load_stock_records, save_visit, save_visits
from service_tracker.models import ServiceVisit, StockRecord


def row(visit_id="V-0001", part_number="P-1001", quantity_used=1, **changes):
    base = ServiceVisit(
        visit_id=visit_id,
        serial_number="SW-4410",
        equipment_type="switch",
        technician="T-01",
        visit_date=date(2026, 10, 1),
        problem_code="PWR",
        part_number=part_number,
        quantity_used=quantity_used,
        outcome="fixed",
    )
    return replace(base, **changes)


@pytest.fixture
def stocked(conn):
    load_stock_records(conn, [
        StockRecord("P-1001", "PSU 500W", 10, 3),
        StockRecord("P-1002", "Fan", 4, 2),
    ])
    return conn


def counts(conn):
    return {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("equipment", "visits", "parts_used", "stock")
    }


def on_hand(conn, part_number):
    return conn.execute(
        "SELECT quantity_on_hand FROM stock WHERE part_number = ?", (part_number,)
    ).fetchone()[0]


def test_saved_visit_stores_everything_and_reduces_stock(stocked):
    save_visit(stocked, [row(quantity_used=2), row(part_number="P-1002", quantity_used=1)])

    assert counts(stocked) == {"equipment": 1, "visits": 1, "parts_used": 2, "stock": 2}
    visit = stocked.execute("SELECT * FROM visits").fetchone()
    assert (visit["serial_number"], visit["visit_date"]) == ("SW-4410", "2026-10-01")
    assert on_hand(stocked, "P-1001") == 8
    assert on_hand(stocked, "P-1002") == 3


def test_failure_halfway_rolls_back_the_whole_visit(stocked):
    before = counts(stocked)
    # The second row breaks CHECK (quantity > 0) after the first row is written.
    with pytest.raises(sqlite3.IntegrityError):
        save_visit(stocked, [row(quantity_used=2), row(part_number="P-1002", quantity_used=0)])

    assert counts(stocked) == before
    assert on_hand(stocked, "P-1001") == 10


def test_stock_may_go_negative(stocked):
    save_visit(stocked, [row(part_number="P-1002", quantity_used=6)])
    assert on_hand(stocked, "P-1002") == -2


def test_part_not_in_stock_is_saved(stocked):
    save_visit(stocked, [row(part_number="P-9999")])
    assert counts(stocked)["parts_used"] == 1
    assert counts(stocked)["stock"] == 2


@pytest.mark.parametrize("field, value", [
    ("serial_number", "SW-9999"),
    ("equipment_type", "router"),
    ("technician", "T-02"),
    ("visit_date", date(2026, 10, 2)),
    ("problem_code", "FAN"),
    ("outcome", "escalated"),
])
def test_rows_that_disagree_raise_value_error(stocked, field, value):
    with pytest.raises(ValueError):
        save_visit(stocked, [row(), row(part_number="P-1002", **{field: value})])
    assert counts(stocked)["visits"] == 0


def test_batch_saves_good_visits_and_reports_the_bad_one(stocked):
    result = save_visits(stocked, [
        row("V-0001"),
        row("V-0002", quantity_used=0),  # fails the CHECK
        row("V-0003", part_number="P-1002"),
    ])

    assert result.saved == 2
    assert result.duplicates == []
    assert [visit_id for visit_id, _ in result.failed] == ["V-0002"]
    assert counts(stocked)["visits"] == 2


def test_running_the_same_batch_twice_changes_nothing(stocked):
    batch = [row("V-0001"), row("V-0001", part_number="P-1002"), row("V-0002")]
    first = save_visits(stocked, batch)
    after_first = counts(stocked)
    stock_after_first = on_hand(stocked, "P-1001")

    second = save_visits(stocked, batch)

    assert first.saved == 2
    assert second.saved == 0
    assert second.duplicates == ["V-0001", "V-0002"]
    assert counts(stocked) == after_first
    assert on_hand(stocked, "P-1001") == stock_after_first
