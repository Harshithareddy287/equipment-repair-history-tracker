"""Frontend helpers read the same database the CLI uses. They do not load CSVs."""

import sys
from pathlib import Path

from service_tracker.cli import main

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
sys.path.insert(0, str(FRONTEND))

import server as frontend  # noqa: E402


def seed_sample(tmp_path, monkeypatch):
    db_path = tmp_path / "ui.db"
    monkeypatch.setenv("SERVICE_DB_PATH", str(db_path))
    assert main([
        "run",
        "--visits", "data/visits.csv",
        "--stock", "data/stock.csv",
        "--settings", "data/settings.json",
        "--db", str(db_path),
    ]) == 0
    return str(db_path)


def test_overview_matches_sample_flags(tmp_path, monkeypatch, capsys):
    db_path = seed_sample(tmp_path, monkeypatch)
    capsys.readouterr()
    data = frontend.overview(db_path)

    assert data["empty"] is False
    assert data["settings"] == {
        "repeat_failure_count": 3,
        "repeat_failure_window_days": 30,
    }
    assert data["counts"] == {
        "repeat_failure": 1,
        "low_stock": 3,
        "shortfall": 1,
        "unknown_part": 0,
    }
    serials = {flag["serial_number"] for flag in data["flags"] if flag["serial_number"]}
    parts = {flag["part_number"] for flag in data["flags"] if flag["part_number"]}
    assert serials == {"SW-4410"}
    assert {"P-1180", "P-2031", "P-3307"} <= parts
    stock_parts = {row["part_number"] for row in data["stock"]}
    assert stock_parts == {"P-1180", "P-2031", "P-3307"}
    shortfall = next(row for row in data["stock"] if row["part_number"] == "P-1180")
    assert shortfall["quantity_on_hand"] == -2
    assert shortfall["status"] == "shortfall"


def test_history_matches_cli_text(tmp_path, monkeypatch, capsys):
    db_path = seed_sample(tmp_path, monkeypatch)
    capsys.readouterr()
    data = frontend.history(db_path, "sw-4410")
    assert data["serial"] == "SW-4410"
    assert [row["visit_id"] for row in data["rows"]] == ["V-0139", "V-0141", "V-0144"]
    assert data["text"].startswith("History for SW-4410\n")
    assert "V-0139  2026-10-02  A. Okafor  PWR  failed  P-1001 x1" in data["text"]


def test_part_lookup_for_shortfall(tmp_path, monkeypatch, capsys):
    db_path = seed_sample(tmp_path, monkeypatch)
    capsys.readouterr()
    data = frontend.part(db_path, "p-1180")
    assert data["found"] is True
    assert data["in_stock_list"] is True
    assert data["stock"]["quantity_on_hand"] == -2
    assert data["stock"]["reorder_level"] == 2
    assert data["stock"]["status"] == "shortfall"
    assert data["uses"][0]["serial_number"] == "RT-2245"
    assert data["uses"][0]["quantity"] == 3


def test_records_lists_every_saved_row(tmp_path, monkeypatch, capsys):
    db_path = seed_sample(tmp_path, monkeypatch)
    capsys.readouterr()
    data = frontend.records(db_path)
    assert data["counts"] == {"visits": 40, "visit_rows": 46, "stock": 12}
    assert any(row["serial_number"] == "SW-4410" for row in data["visits"])
    assert any(row["part_number"] == "P-1180" and row["status"] == "shortfall" for row in data["stock"])


def test_search_finds_parts_by_name(tmp_path, monkeypatch, capsys):
    db_path = seed_sample(tmp_path, monkeypatch)
    capsys.readouterr()
    data = frontend.search(db_path, "Fan")
    assert data["machine"] is None
    assert [row["part_number"] for row in data["parts"]] == ["P-1002", "P-3307"]
    assert data["parts"][0]["stock"]["description"] == "Chassis fan"
    assert data["parts"][1]["stock"]["description"] == "Fan tray"


def test_unknown_lookup_is_empty(tmp_path, monkeypatch, capsys):
    db_path = seed_sample(tmp_path, monkeypatch)
    capsys.readouterr()
    assert frontend.history(db_path, "NO-SUCH")["rows"] == []
    missing = frontend.part(db_path, "NO-SUCH")
    assert missing["found"] is False
    assert missing["text"] == "No stock record or usage for NO-SUCH."


def test_guided_whitelist():
    assert frontend.parse_guided("help") == ("help", None)
    assert frontend.parse_guided("version") == ("version", None)
    assert frontend.parse_guided("history SW-4410") == ("history", "SW-4410")
    assert frontend.parse_guided("report") == ("report", None)
    kind, message = frontend.parse_guided("ls")
    assert kind == "error"
    assert "unknown command: ls" in message
    kind, message = frontend.parse_guided("run")
    assert kind == "error"
    assert "not available in the UI" in message


def test_guided_history_and_report(tmp_path, monkeypatch, capsys):
    db_path = seed_sample(tmp_path, monkeypatch)
    capsys.readouterr()
    ok, output = frontend.run_guided(db_path, "history SW-4410")
    assert ok is True
    assert output.startswith("History for SW-4410")
    ok, output = frontend.run_guided(db_path, "report")
    assert ok is True
    assert "SW-4410" in output
    assert "P-1180" in output
    ok, output = frontend.run_guided(db_path, "ls")
    assert ok is False
    assert "unknown command: ls" in output
