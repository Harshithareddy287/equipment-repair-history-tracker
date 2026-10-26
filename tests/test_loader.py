"""load_visits and load_stock turn good rows into models and bad rows into Rejections."""

from datetime import date
from pathlib import Path

import pytest

from service_tracker.loader import (
    InputFileError,
    format_rejections,
    load_stock,
    load_visits,
)
from service_tracker.models import Rejection, ServiceVisit, StockRecord

PATTERN = "^P-\\d{4}$"
DATA = Path(__file__).parent.parent / "data"
VISIT_HEADER = (
    "visit_id,serial_number,equipment_type,technician,visit_date,"
    "problem_code,part_number,quantity_used,outcome"
)
STOCK_HEADER = "part_number,description,quantity_on_hand,reorder_level"
GOOD_VISIT = "V-0101,SW-4410,switch,A. Okafor,2026-10-02,PWR,P-1001,2,fixed"


def write(tmp_path, header, *rows, name="file.csv", encoding="utf-8"):
    path = tmp_path / name
    path.write_text("\n".join([header, *rows]) + "\n", encoding=encoding)
    return path


def visits_from(tmp_path, *rows, **kwargs):
    return load_visits(write(tmp_path, VISIT_HEADER, *rows, **kwargs), PATTERN)


def stock_from(tmp_path, *rows):
    return load_stock(write(tmp_path, STOCK_HEADER, *rows))


def raw_visit(line):
    return dict(zip(VISIT_HEADER.split(","), line.split(",")))


# --- visits -----------------------------------------------------------------


def test_valid_visit_parses_to_date_and_int(tmp_path):
    visits, rejections = visits_from(tmp_path, GOOD_VISIT)
    assert rejections == []
    assert visits == [ServiceVisit(
        "V-0101", "SW-4410", "switch", "A. Okafor", date(2026, 10, 2),
        "PWR", "P-1001", 2, "fixed",
    )]


@pytest.mark.parametrize("row, reason", [
    (",SW-4410,switch,A. Okafor,2026-10-02,PWR,P-1001,2,fixed",
     "visit_id is missing"),
    ("V-0107,,router,A. Okafor,2026-10-02,PWR,P-1001,2,fixed",
     "serial_number is missing"),
    ("V-0125,SW-4410,switch,A. Okafor,2026-13-05,PWR,P-1001,2,fixed",
     "visit_date is not an ISO date (2026-13-05)"),
    ("V-0134,SW-4410,switch,A. Okafor,2026-10-02,PWR,P-1001,two,fixed",
     "quantity_used is not a whole number (two)"),
    ("V-0116,SW-4410,switch,A. Okafor,2026-10-02,PWR,P-1001,-2,fixed",
     "quantity_used is negative (-2)"),
    ("V-0101,SW-4410,switch,A. Okafor,2026-10-02,PWR,P-1001,0,fixed",
     "quantity_used is zero"),
    ("V-0101,SW-4410,switch,A. Okafor,2026-10-02,PWR,P-1001,2,repaired",
     "outcome is not one of escalated, failed, fixed, replaced_part (repaired)"),
    ("V-0101,SW-4410,switch,A. Okafor,2026-10-02,PWR,X-12,2,fixed",
     "part_number does not match ^P-\\d{4}$ (X-12)"),
    ("V-0101,SW-4410,switch,A. Okafor,2026-10-02,PWR,,2,fixed",
     "part_number is missing"),
])
def test_bad_visit_is_rejected(tmp_path, row, reason):
    visits, rejections = visits_from(tmp_path, GOOD_VISIT, row)
    assert len(visits) == 1
    assert rejections == [Rejection("visits", 3, raw_visit(row), f"line 3: {reason}")]


@pytest.mark.parametrize("value", ["20261002", "2026-W40-5", "2026-10-2", "٢٠٢٦-10-02"])
def test_only_yyyy_mm_dd_dates_are_accepted(tmp_path, value):
    row = GOOD_VISIT.replace("2026-10-02", value)
    _, rejections = visits_from(tmp_path, row)
    assert rejections[0].reason == f"line 2: visit_date is not an ISO date ({value})"


@pytest.mark.parametrize("value", ["3_000", "+3", "2.0", "٣"])
def test_only_plain_whole_numbers_are_accepted(tmp_path, value):
    row = GOOD_VISIT.replace(",2,fixed", f",{value},fixed")
    _, rejections = visits_from(tmp_path, row)
    assert rejections[0].reason == f"line 2: quantity_used is not a whole number ({value})"


def test_first_failing_check_is_the_reason(tmp_path):
    row = "V-0101,,switch,A. Okafor,2026-13-05,PWR,P-1001,-2,fixed"
    _, rejections = visits_from(tmp_path, row)
    assert rejections[0].reason == "line 2: serial_number is missing"


def test_fields_are_normalised_before_checks(tmp_path):
    row = " V-0101 , sw-4410 ,switch, A. Okafor , 2026-10-02 ,PWR, p-1001 , 2 , fixed "
    visits, rejections = visits_from(tmp_path, row)
    assert rejections == []
    v = visits[0]
    assert (v.visit_id, v.serial_number, v.part_number, v.technician) == (
        "V-0101", "SW-4410", "P-1001", "A. Okafor"
    )
    assert (v.visit_date, v.quantity_used, v.outcome) == (date(2026, 10, 2), 2, "fixed")


def test_raw_keeps_the_row_as_read(tmp_path):
    row = "V-0101, sw-4410 ,switch,A. Okafor,2026-10-02,PWR,p-1001,0,fixed"
    _, rejections = visits_from(tmp_path, row)
    assert rejections[0].raw["serial_number"] == " sw-4410 "
    assert rejections[0].raw["part_number"] == "p-1001"


def test_file_with_bom_loads(tmp_path):
    visits, rejections = visits_from(tmp_path, GOOD_VISIT, encoding="utf-8-sig")
    assert rejections == [] and visits[0].visit_id == "V-0101"


def test_short_row_is_rejected_not_crashed(tmp_path):
    _, rejections = visits_from(tmp_path, "V-0101,SW-4410,switch")
    assert rejections[0].reason == "line 2: visit_date is not an ISO date ()"


def test_line_numbers_count_the_header_and_blank_lines(tmp_path):
    bad = GOOD_VISIT.replace(",2,fixed", ",0,fixed")
    _, rejections = visits_from(tmp_path, GOOD_VISIT, "", bad)
    assert rejections[0].line_number == 4
    assert rejections[0].reason.startswith("line 4: ")


def test_missing_visit_column(tmp_path):
    path = write(tmp_path, VISIT_HEADER.replace(",outcome", ""), GOOD_VISIT)
    with pytest.raises(InputFileError) as e:
        load_visits(path, PATTERN)
    assert str(e.value) == f'input error: {path} is missing column "outcome"'


def test_empty_file_is_missing_columns(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("")
    with pytest.raises(InputFileError, match='missing column "visit_id"'):
        load_visits(path, PATTERN)


def test_missing_visit_file(tmp_path):
    path = tmp_path / "nope.csv"
    with pytest.raises(InputFileError) as e:
        load_visits(path, PATTERN)
    assert str(e.value) == f"input error: {path} not found"


# --- stock ------------------------------------------------------------------


def test_valid_stock(tmp_path):
    records, rejections = stock_from(tmp_path, "P-2031,PSU 750W,4,5", " p-1180 ,SFP+,1,2")
    assert rejections == []
    assert records == [
        StockRecord("P-2031", "PSU 750W", 4, 5),
        StockRecord("P-1180", "SFP+", 1, 2),
    ]


@pytest.mark.parametrize("row, reason", [
    (",Fan,4,5", "part_number is missing"),
    ("p-2031,Again,9,9", "part_number is a duplicate of line 2 (P-2031)"),
    ("P-3307,Fan tray,-1,4", "quantity_on_hand is negative (-1)"),
    ("P-3307,Fan tray,lots,4", "quantity_on_hand is not a whole number (lots)"),
    ("P-3307,Fan tray,6,-4", "reorder_level is negative (-4)"),
    ("P-3307,Fan tray,6,4.5", "reorder_level is not a whole number (4.5)"),
])
def test_bad_stock_is_rejected(tmp_path, row, reason):
    records, rejections = stock_from(tmp_path, "P-2031,PSU 750W,4,5", row)
    assert [r.part_number for r in records] == ["P-2031"]
    raw = dict(zip(STOCK_HEADER.split(","), row.split(",")))
    assert rejections == [Rejection("stock", 3, raw, f"line 3: {reason}")]


def test_zero_stock_is_allowed(tmp_path):
    records, rejections = stock_from(tmp_path, "P-2031,PSU 750W,0,0")
    assert rejections == [] and records[0].quantity_on_hand == 0


def test_missing_stock_column(tmp_path):
    path = write(tmp_path, "part_number,description,quantity_on_hand", "P-2031,PSU,4")
    with pytest.raises(InputFileError, match='missing column "reorder_level"'):
        load_stock(path)


def test_missing_stock_file(tmp_path):
    with pytest.raises(InputFileError, match="not found"):
        load_stock(tmp_path / "nope.csv")


# --- format_rejections ------------------------------------------------------


def test_format_no_rejections():
    assert format_rejections([]) == "No rows rejected."


def test_format_lists_each_reason():
    rejections = [
        Rejection("visits", 9, {}, "line 9: serial_number is missing"),
        Rejection("visits", 18, {}, "line 18: quantity_used is negative (-2)"),
    ]
    assert format_rejections(rejections) == (
        "2 rows rejected:\n"
        "line 9: serial_number is missing\n"
        "line 18: quantity_used is negative (-2)"
    )


# --- the generated data/ files ----------------------------------------------


@pytest.mark.parametrize("name", ["visits.csv", "visits_unknown_parts.csv"])
def test_generated_visits_reject_only_the_planted_bad_rows(name):
    visits, rejections = load_visits(DATA / name, PATTERN)
    assert sorted(r.raw["visit_id"] for r in rejections) == [
        "V-0107", "V-0116", "V-0125", "V-0134"
    ]
    extra = 2 if name == "visits_unknown_parts.csv" else 0
    assert len({v.visit_id for v in visits}) == 40 + extra
    assert len(visits) == 46 + extra


def test_generated_stock_has_no_rejections():
    records, rejections = load_stock(DATA / "stock.csv")
    assert rejections == [] and len(records) == 12
