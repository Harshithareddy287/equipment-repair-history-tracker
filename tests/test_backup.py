"""The backup copy must match the source and pass the integrity check."""

import sqlite3

from service_tracker.backup import backup


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
