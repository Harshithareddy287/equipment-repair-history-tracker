"""Run the whole tool once against the committed synthetic files."""

import sqlite3

from service_tracker.cli import main


def test_full_run(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "it.db"
    monkeypatch.setenv("SERVICE_DB_PATH", str(db_path))

    assert main([
        "run",
        "--visits", "data/visits.csv",
        "--stock", "data/stock.csv",
        "--settings", "data/settings.json",
    ]) == 0

    report = capsys.readouterr().out
    assert "SW-4410" in report
    assert "P-2031" in report
    assert "P-3307" in report
    assert "P-1180" in report
    assert "4 rows rejected:" in report

    connection = sqlite3.connect(db_path)
    try:
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("visits", "parts_used", "stock")
        }
    finally:
        connection.close()

    assert counts == {"visits": 40, "parts_used": 46, "stock": 12}
