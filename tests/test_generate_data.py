"""The generator is repeatable and plants every case the demo needs."""

import csv
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "scripts" / "generate_data.py"
FILES = ["visits.csv", "stock.csv", "settings.json", "visits_unknown_parts.csv"]
OUTCOMES = {"fixed", "failed", "replaced_part", "escalated"}


def generate(out, *args):
    subprocess.run([sys.executable, str(SCRIPT), "--out", str(out), *args], check=True)
    return out


def read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def is_clean(row):
    """A simple stand-in for the loader's checks, enough to count the planted cases."""
    try:
        date.fromisoformat(row["visit_date"])
        quantity = int(row["quantity_used"])
    except ValueError:
        return False
    return bool(row["serial_number"]) and quantity > 0


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    out = generate(tmp_path_factory.mktemp("seed42"), "--seed", "42", "--with-unknown-parts")
    visits = read(out / "visits.csv")
    return {
        "out": out,
        "visits": visits,
        "clean": [r for r in visits if is_clean(r)],
        "bad": [r for r in visits if not is_clean(r)],
        "stock": {r["part_number"]: r for r in read(out / "stock.csv")},
    }


def stock_after_usage(data):
    left = {p: int(r["quantity_on_hand"]) for p, r in data["stock"].items()}
    for row in data["clean"]:
        left[row["part_number"]] -= int(row["quantity_used"])
    return left


def test_same_seed_gives_identical_files(tmp_path):
    a = generate(tmp_path / "a", "--seed", "7", "--with-unknown-parts")
    b = generate(tmp_path / "b", "--seed", "7", "--with-unknown-parts")
    for name in FILES:
        assert (a / name).read_bytes() == (b / name).read_bytes(), name


def test_different_seed_gives_different_visits(tmp_path):
    a = generate(tmp_path / "a", "--seed", "1")
    b = generate(tmp_path / "b", "--seed", "2")
    assert (a / "visits.csv").read_bytes() != (b / "visits.csv").read_bytes()


def test_committed_data_matches_seed_42(data):
    for name in FILES:
        assert (ROOT / "data" / name).read_bytes() == (data["out"] / name).read_bytes(), name


def test_all_files_parse_with_dict_reader(data):
    for name in ["visits.csv", "stock.csv", "visits_unknown_parts.csv"]:
        rows = read(data["out"] / name)
        assert rows and all(None not in r and None not in r.values() for r in rows), name


def test_clean_visits_cover_serials_and_technicians(data):
    clean = data["clean"]
    assert len({r["visit_id"] for r in clean}) == 40
    assert len({r["serial_number"] for r in clean}) == 15
    assert len({r["technician"] for r in clean}) == 4
    rows_per_visit = defaultdict(int)
    for r in clean:
        rows_per_visit[r["visit_id"]] += 1
    assert max(rows_per_visit.values()) == 2  # some visits used two parts


def test_only_sw_4410_is_a_repeat_failure(data):
    dates = defaultdict(set)
    for r in data["clean"]:
        dates[r["serial_number"]].add(date.fromisoformat(r["visit_date"]))
    flagged = set()
    for serial, days in dates.items():
        days = sorted(days)
        if any(days[i + 2] - days[i] <= timedelta(days=31) for i in range(len(days) - 2)):
            flagged.add(serial)
    assert flagged == {"SW-4410"}
    assert sorted(dates["SW-4410"]) == [date(2026, 10, 2), date(2026, 10, 11), date(2026, 10, 24)]


def test_low_stock_and_shortfall(data):
    left = stock_after_usage(data)
    reorder = {p: int(r["reorder_level"]) for p, r in data["stock"].items()}
    low = {p for p in left if left[p] <= reorder[p]}
    assert low == {"P-2031", "P-3307", "P-1180"}
    assert (left["P-2031"], reorder["P-2031"]) == (2, 5)
    assert left["P-3307"] == reorder["P-3307"] == 4
    assert {p for p in left if left[p] < 0} == {"P-1180"}
    assert data["stock"]["P-1180"]["quantity_on_hand"] == "1"
    assert left["P-1180"] == -2


def test_bad_rows_are_planted(data):
    bad = {r["visit_id"]: r for r in data["bad"]}
    assert len(bad) == 4
    assert bad["V-0107"]["serial_number"] == ""
    assert {r["quantity_used"] for r in bad.values()} >= {"-2", "two"}
    assert "2026-13-05" in {r["visit_date"] for r in bad.values()}


def test_part_numbers_and_outcomes_are_valid(data):
    pattern = re.compile(r"^P-\d{4}$")
    for row in data["visits"]:
        assert pattern.match(row["part_number"]), row
        assert row["outcome"] in OUTCOMES, row
    assert all(pattern.match(p) for p in data["stock"])


def test_unknown_parts_file_adds_two_visits(data):
    extra_file = read(data["out"] / "visits_unknown_parts.csv")
    assert extra_file[: len(data["visits"])] == data["visits"]
    extra = extra_file[len(data["visits"]):]
    assert [r["part_number"] for r in extra] == ["P-9901", "P-9902"]
    assert len({r["visit_id"] for r in extra}) == 2
    assert all(is_clean(r) and r["part_number"] not in data["stock"] for r in extra)


def test_flag_does_not_change_other_files(tmp_path):
    plain = generate(tmp_path / "plain", "--seed", "42")
    flagged = generate(tmp_path / "flagged", "--seed", "42", "--with-unknown-parts")
    assert not (plain / "visits_unknown_parts.csv").exists()
    for name in ["visits.csv", "stock.csv", "settings.json"]:
        assert (plain / name).read_bytes() == (flagged / name).read_bytes(), name
