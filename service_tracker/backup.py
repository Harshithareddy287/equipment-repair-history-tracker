"""Copy a SQLite database and check the copy."""

import sqlite3
import sys
from contextlib import closing
from pathlib import Path


def backup(src, dest) -> str:
    """Copy src to dest with Connection.backup, then check the copy.

    Returns "ok" when PRAGMA integrity_check passes. Raises FileNotFoundError
    when src is missing, and RuntimeError when the copy is not intact.
    Creates the destination directory if needed.
    """
    if not Path(src).is_file():
        raise FileNotFoundError(f"backup error: {src} not found")
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(src)) as source, closing(sqlite3.connect(dest)) as target:
        source.backup(target)
        (result,) = target.execute("PRAGMA integrity_check").fetchone()
    if result != "ok":
        raise RuntimeError(f"backup failed integrity check: {result}")
    return result


def main(argv: list[str] | None = None) -> int:
    """Run ``python -m service_tracker.backup SRC DEST``."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print("usage: python -m service_tracker.backup SRC DEST", file=sys.stderr)
        return 2
    try:
        print(backup(args[0], args[1]))
    except FileNotFoundError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
