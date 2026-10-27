"""The backup copy must match the source and pass the integrity check."""

import sqlite3

import pytest

from service_tracker.backup import backup, main


def _counts(path):
    connection = sqlite3.connect(path)
    try:
        return {
            "visits": connection.execute("SELECT COUNT(*) FROM visits").fetchone()[0],
            "stock": connection.execute("SELECT COUNT(*) FROM stock").fetchone()[0],
        }
    finally:
        connection.close()


def test_backup_copies_rows_and_passes_integrity_check(tmp_path):
    source = tmp_path / "service.db"
    destination = tmp_path / "backups" / "pre-1.1.0.db"
    connection = sqlite3.connect(source)
    connection.executescript(
        """
        CREATE TABLE visits (visit_id TEXT PRIMARY KEY);
        CREATE TABLE stock (part_number TEXT PRIMARY KEY);
        INSERT INTO visits VALUES ('V-0139'), ('V-0141'), ('V-0144');
        INSERT INTO stock VALUES ('P-2031'), ('P-1180');
        """
    )
    connection.commit()
    connection.close()

    assert backup(source, destination) == "ok"
    assert destination.is_file()
    assert _counts(destination) == _counts(source) == {
        "visits": 3,
        "stock": 2,
    }


def test_backup_rejects_a_missing_source(tmp_path):
    missing = tmp_path / "typo.db"
    destination = tmp_path / "backups" / "x.db"
    with pytest.raises(FileNotFoundError, match="not found"):
        backup(missing, destination)
    assert not missing.exists()
    assert not destination.exists()


def test_main_prints_a_missing_source(tmp_path, capsys):
    missing = tmp_path / "typo.db"
    destination = tmp_path / "backups" / "x.db"
    code = main([str(missing), str(destination)])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err == f"backup error: {missing} not found\n"
    assert captured.out == ""
    assert not missing.exists()
    assert not destination.exists()
