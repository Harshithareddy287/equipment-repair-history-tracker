"""Rules engine: repeat failure, low stock, stock shortfall, and unknown part.

Each test inserts its own rows into the conn fixture. The rules read that
database. They do not read the CSV files.
"""

import dataclasses
from datetime import date, timedelta

import pytest

from service_tracker.db import load_stock_records, save_visits
from service_tracker.models import ServiceVisit, StockRecord
from service_tracker.report import RunSummary, render_report
from service_tracker.rules import RULES, run_all_rules
from service_tracker.rules.base import Flag, FlagRule
from service_tracker.rules.low_stock import LowStockRule
from service_tracker.rules.repeat_failure import RepeatFailureRule
from service_tracker.rules.shortfall import ShortfallRule
from service_tracker.rules.unknown_part import UnknownPartRule
from service_tracker.settings import Settings


def make_settings(count=3, window_days=30):
    return Settings(
        repeat_failure_count=count,
        repeat_failure_window_days=window_days,
        part_number_pattern="^P-\\d{4}$",
    )


def insert_visits(conn, serial, dates):
    with conn:
        conn.execute(
            "INSERT INTO equipment (serial_number, equipment_type) VALUES (?, ?)",
            (serial, "switch"),
        )
        for index, visit_date in enumerate(dates, start=1):
            conn.execute(
                "INSERT INTO visits (visit_id, serial_number, technician, visit_date,"
                " problem_code, outcome) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    f"{serial}-{index}",
                    serial,
                    "T-01",
                    visit_date.isoformat(),
                    "PWR",
                    "fixed",
                ),
            )


def insert_part(conn, part_number, quantity_on_hand, reorder_level):
    with conn:
        conn.execute(
            "INSERT INTO stock (part_number, description, quantity_on_hand, reorder_level)"
            " VALUES (?, ?, ?, ?)",
            (part_number, "test part", quantity_on_hand, reorder_level),
        )


def insert_part_used(conn, visit_id, part_number, quantity=1):
    with conn:
        conn.execute(
            "INSERT INTO parts_used (visit_id, part_number, quantity) VALUES (?, ?, ?)",
            (visit_id, part_number, quantity),
        )


def test_repeat_failure_triggers_at_the_configured_threshold(conn):
    # All four visits sit inside 30 days of January 1, so the one flag keeps all four.
    dates = [date(2026, 1, 1), date(2026, 1, 5), date(2026, 1, 10), date(2026, 1, 20)]
    insert_visits(conn, "SN-100", dates)
    flags = RepeatFailureRule().evaluate(conn, make_settings(count=3, window_days=30))
    assert flags == [
        Flag(
            rule="repeat_failure",
            serial_number="SN-100",
            part_number=None,
            visit_dates=dates,
            quantity=None,
            message="SN-100: 4 visits in 19 days (limit 3 in 30)",
        )
    ]


def test_repeat_failure_does_not_trigger_below_the_threshold(conn):
    insert_visits(conn, "SN-100", [date(2026, 4, 1), date(2026, 4, 5)])
    assert RepeatFailureRule().evaluate(conn, make_settings(count=3, window_days=30)) == []


def test_visits_exactly_window_days_apart(conn):
    window_days = 10
    start = date(2026, 5, 1)
    dates = [start, start + timedelta(days=4), start + timedelta(days=window_days)]
    insert_visits(conn, "SN-100", dates)
    flags = RepeatFailureRule().evaluate(conn, make_settings(count=3, window_days=window_days))
    assert [flag.visit_dates for flag in flags] == [dates]
    assert flags[0].message == "SN-100: 3 visits in 10 days (limit 3 in 10)"


def test_visits_outside_the_configured_window(conn):
    window_days = 10
    start = date(2026, 5, 1)
    dates = [start, start + timedelta(days=4), start + timedelta(days=window_days + 1)]
    insert_visits(conn, "SN-100", dates)
    assert RepeatFailureRule().evaluate(conn, make_settings(count=3, window_days=window_days)) == []


def test_changing_repeat_failure_count_changes_results(conn):
    insert_visits(conn, "SN-100", [date(2026, 4, 1), date(2026, 4, 5)])
    flagged = RepeatFailureRule().evaluate(conn, make_settings(count=2, window_days=30))
    assert flagged == [
        Flag(
            rule="repeat_failure",
            serial_number="SN-100",
            part_number=None,
            visit_dates=[date(2026, 4, 1), date(2026, 4, 5)],
            quantity=None,
            message="SN-100: 2 visits in 4 days (limit 2 in 30)",
        )
    ]
    assert RepeatFailureRule().evaluate(conn, make_settings(count=3, window_days=30)) == []


def test_one_repeat_failure_flag_per_serial(conn):
    insert_visits(
        conn,
        "SN-100",
        [date(2026, 1, 1), date(2026, 1, 5), date(2026, 1, 10), date(2026, 1, 20)],
    )
    insert_visits(conn, "SN-200", [date(2026, 4, 2), date(2026, 4, 3), date(2026, 4, 4)])
    flags = RepeatFailureRule().evaluate(conn, make_settings(count=3, window_days=30))
    assert [flag.serial_number for flag in flags] == ["SN-100", "SN-200"]
    assert len(flags) == 2


def test_repeat_failure_slides_past_an_older_visit(conn):
    insert_visits(
        conn,
        "SN-100",
        [date(2026, 1, 1), date(2026, 3, 1), date(2026, 3, 10), date(2026, 3, 20)],
    )
    flags = RepeatFailureRule().evaluate(conn, make_settings(count=3, window_days=30))
    assert len(flags) == 1
    assert flags[0].visit_dates == [date(2026, 3, 1), date(2026, 3, 10), date(2026, 3, 20)]
    assert flags[0].message == "SN-100: 3 visits in 19 days (limit 3 in 30)"


def test_low_stock_below_reorder_level(conn):
    insert_part(conn, "P-7001", 2, 5)
    insert_part(conn, "P-7002", 9, 3)
    flags = LowStockRule().evaluate(conn, make_settings())
    assert flags == [
        Flag(
            rule="low_stock",
            serial_number=None,
            part_number="P-7001",
            visit_dates=[],
            quantity=2,
            message="P-7001 has 2 on hand, at or below its reorder level of 5",
        )
    ]


def test_stock_exactly_equal_to_reorder_level_is_low_stock(conn):
    insert_part(conn, "P-7001", 5, 5)
    flags = LowStockRule().evaluate(conn, make_settings())
    assert len(flags) == 1
    assert flags[0].part_number == "P-7001"
    assert flags[0].quantity == 5


def test_healthy_stock_produces_no_low_stock_flag(conn):
    insert_part(conn, "P-7001", 6, 5)
    assert LowStockRule().evaluate(conn, make_settings()) == []


def test_negative_stock_produces_a_shortfall(conn):
    insert_part(conn, "P-8001", -2, 1)
    flags = ShortfallRule().evaluate(conn, make_settings())
    assert flags == [
        Flag(
            rule="shortfall",
            serial_number=None,
            part_number="P-8001",
            visit_dates=[],
            quantity=-2,
            message="P-8001: -2 on hand",
        )
    ]


def test_zero_stock_is_not_a_shortfall(conn):
    insert_part(conn, "P-8001", 0, 5)
    assert ShortfallRule().evaluate(conn, make_settings()) == []


def test_multiple_rules_produce_multiple_flags(conn):
    insert_visits(
        conn,
        "SN-100",
        [date(2026, 7, 1), date(2026, 7, 8), date(2026, 7, 15)],
    )
    insert_part(conn, "P-1001", 2, 5)
    insert_part(conn, "P-2002", -3, 1)
    assert run_all_rules(conn, make_settings(count=3, window_days=30)) == [
        Flag(
            rule="repeat_failure",
            serial_number="SN-100",
            part_number=None,
            visit_dates=[date(2026, 7, 1), date(2026, 7, 8), date(2026, 7, 15)],
            quantity=None,
            message="SN-100: 3 visits in 14 days (limit 3 in 30)",
        ),
        Flag(
            rule="low_stock",
            serial_number=None,
            part_number="P-1001",
            visit_dates=[],
            quantity=2,
            message="P-1001 has 2 on hand, at or below its reorder level of 5",
        ),
        Flag(
            rule="low_stock",
            serial_number=None,
            part_number="P-2002",
            visit_dates=[],
            quantity=-3,
            message="P-2002 has -3 on hand, at or below its reorder level of 1",
        ),
        Flag(
            rule="shortfall",
            serial_number=None,
            part_number="P-2002",
            visit_dates=[],
            quantity=-3,
            message="P-2002: -3 on hand",
        ),
    ]


def test_empty_database_produces_no_flags(conn):
    assert run_all_rules(conn, make_settings()) == []
    assert conn.execute("SELECT 1").fetchone()[0] == 1


def test_healthy_database_produces_no_flags(conn):
    insert_visits(conn, "SN-100", [date(2026, 4, 1), date(2026, 6, 1)])
    insert_part(conn, "P-7001", 10, 2)
    assert run_all_rules(conn, make_settings()) == []


def test_abstract_flag_rule_cannot_be_instantiated():
    with pytest.raises(TypeError):
        FlagRule()


def test_flag_cannot_be_changed():
    flag = Flag("low_stock", None, "P-7001", [], 2, "low")
    with pytest.raises(dataclasses.FrozenInstanceError):
        flag.quantity = 0


def test_rules_registry_lists_each_rule_once():
    assert [type(rule) for rule in RULES] == [
        RepeatFailureRule,
        LowStockRule,
        ShortfallRule,
        UnknownPartRule,
    ]


# --- unknown part -----------------------------------------------------------


def test_unknown_part_is_flagged(conn):
    insert_visits(conn, "SN-100", [date(2026, 10, 1)])
    insert_part(conn, "P-1001", 10, 2)
    insert_part_used(conn, "SN-100-1", "P-1001", 1)
    insert_part_used(conn, "SN-100-1", "P-9901", 2)
    flags = UnknownPartRule().evaluate(conn, make_settings())
    assert flags == [
        Flag(
            rule="unknown_part",
            serial_number="SN-100",
            part_number="P-9901",
            visit_dates=[date(2026, 10, 1)],
            quantity=2,
            message="P-9901 is not in stock",
        )
    ]


def test_known_parts_produce_no_unknown_part_flag(conn):
    insert_visits(conn, "SN-100", [date(2026, 10, 1)])
    insert_part(conn, "P-1001", 10, 2)
    insert_part_used(conn, "SN-100-1", "P-1001", 1)
    assert UnknownPartRule().evaluate(conn, make_settings()) == []


def test_each_unknown_part_reference_is_flagged_once_in_query_order(conn):
    # The later visit is inserted first. The query orders by date, then part id.
    insert_visits(conn, "SN-200", [date(2026, 10, 20)])
    insert_visits(conn, "SN-100", [date(2026, 10, 1), date(2026, 10, 5)])
    insert_part(conn, "P-1001", 10, 2)
    insert_part_used(conn, "SN-200-1", "P-9901", 4)
    insert_part_used(conn, "SN-100-1", "P-9902", 1)
    insert_part_used(conn, "SN-100-1", "P-9901", 2)
    insert_part_used(conn, "SN-100-2", "P-9901", 3)
    insert_part_used(conn, "SN-100-1", "P-1001", 1)
    flags = UnknownPartRule().evaluate(conn, make_settings())
    assert [(flag.part_number, flag.visit_dates, flag.quantity) for flag in flags] == [
        ("P-9902", [date(2026, 10, 1)], 1),
        ("P-9901", [date(2026, 10, 1)], 2),
        ("P-9901", [date(2026, 10, 5)], 3),
        ("P-9901", [date(2026, 10, 20)], 4),
    ]


def test_unknown_part_on_an_empty_database(conn):
    assert UnknownPartRule().evaluate(conn, make_settings()) == []


def test_unknown_part_message_and_fields_come_from_the_row(conn):
    insert_visits(conn, "SN-100", [date(2026, 8, 3)])
    insert_part_used(conn, "SN-100-1", "P-9901", 7)
    flag = UnknownPartRule().evaluate(conn, make_settings())[0]
    assert flag.rule == "unknown_part"
    assert flag.serial_number == "SN-100"
    assert flag.part_number == "P-9901"
    assert flag.visit_dates == [date(2026, 8, 3)]
    assert flag.quantity == 7
    assert "P-9901" in flag.message
    assert flag.message == "P-9901 is not in stock"


def test_unknown_part_is_registered_and_runs_with_the_other_rules(conn):
    assert [type(rule) for rule in RULES].count(UnknownPartRule) == 1
    insert_visits(
        conn,
        "SN-100",
        [date(2026, 7, 1), date(2026, 7, 8), date(2026, 7, 15)],
    )
    insert_part_used(conn, "SN-100-1", "P-9901", 1)
    flags = run_all_rules(conn, make_settings(count=3, window_days=30))
    assert [flag.rule for flag in flags] == ["repeat_failure", "unknown_part"]
    assert flags[0].serial_number == "SN-100"
    assert flags[1].part_number == "P-9901"


def test_unknown_part_remains_after_save_visits(conn):
    load_stock_records(conn, [StockRecord("P-1001", "known part", 10, 2)])
    result = save_visits(
        conn,
        [
            ServiceVisit(
                "V-1", "SN-100", "switch", "T-01", date(2026, 10, 1),
                "PWR", "P-1001", 1, "fixed",
            ),
            ServiceVisit(
                "V-1", "SN-100", "switch", "T-01", date(2026, 10, 1),
                "PWR", "P-9901", 2, "fixed",
            ),
        ],
    )
    assert result.saved == 1
    assert result.failed == []
    flags = UnknownPartRule().evaluate(conn, make_settings())
    assert [flag.part_number for flag in flags] == ["P-9901"]
    assert flags[0].quantity == 2


def test_report_lists_unknown_part_after_the_known_groups(conn):
    insert_part(conn, "P-1001", 1, 5)
    insert_visits(conn, "SN-100", [date(2026, 10, 1)])
    insert_part_used(conn, "SN-100-1", "P-9901", 1)
    text = render_report(
        run_all_rules(conn, make_settings()),
        RunSummary(1, 1, 0, 0, 1),
    )
    assert text.index("Low stock") < text.index("Unknown part")
    assert "P-9901 is not in stock" in text
    assert "Repeat failures" not in text
    assert "Stock shortfalls" not in text
