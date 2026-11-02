#!/usr/bin/env python3
"""Local Owner / Technical UI for the Service Visit Tracker.

Serves the static files in this folder and a small JSON API that reads
the existing SQLite history through service_tracker. It does not change
the package, and it does not load CSV files.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from contextlib import closing
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from service_tracker import __version__
from service_tracker.cli import format_history
from service_tracker.db import connect, history_for_serial, init_db, low_stock_parts
from service_tracker.report import RunSummary, render_report
from service_tracker.rules import run_all_rules
from service_tracker.settings import SettingsError, load_settings

RULE_LABELS = {
    "repeat_failure": "Repeat failure",
    "low_stock": "Low stock",
    "shortfall": "Shortfall",
    "unknown_part": "Unknown part",
}
GUIDED_HELP = """Guided commands

  help                 this list
  version              package version
  history SERIAL       visits already saved for one machine
  report               flags from the saved history

Free-form commands are not available yet.
Load files with the real CLI, for example:

  service-tracker run --visits data/visits.csv --stock data/stock.csv \\
      --settings data/settings.json --db demo.db
"""


def resolve_db_path(cli_path: str | None) -> str:
    """Match connect(): --db, then SERVICE_DB_PATH, then a local default."""
    if cli_path:
        return cli_path
    env = os.environ.get("SERVICE_DB_PATH")
    if env:
        return env
    demo = ROOT / "demo.db"
    if demo.is_file():
        return str(demo)
    return str(ROOT / "service.db")


def resolve_settings_path() -> Path:
    return ROOT / "data" / "settings.json"


def flag_payload(flag) -> dict:
    return {
        "rule": flag.rule,
        "label": RULE_LABELS.get(flag.rule, flag.rule.replace("_", " ").title()),
        "serial_number": flag.serial_number,
        "part_number": flag.part_number,
        "visit_dates": [day.isoformat() for day in flag.visit_dates],
        "quantity": flag.quantity,
        "message": flag.message,
    }


def open_db(db_path: str):
    conn = connect(db_path)
    init_db(conn)
    return conn


def stock_payload(row: dict) -> dict:
    quantity = row["quantity_on_hand"]
    reorder = row["reorder_level"]
    if quantity < 0:
        status = "shortfall"
    elif quantity <= reorder:
        status = "low_stock"
    else:
        status = "ok"
    return {
        "part_number": row["part_number"],
        "description": row["description"],
        "quantity_on_hand": quantity,
        "reorder_level": reorder,
        "status": status,
    }


def overview(db_path: str) -> dict:
    settings = load_settings(resolve_settings_path())
    with closing(open_db(db_path)) as conn:
        visit_count = conn.execute("SELECT COUNT(*) FROM visits").fetchone()[0]
        flags = run_all_rules(conn, settings)
        stock = [stock_payload(row) for row in low_stock_parts(conn)]
    counts = {rule: 0 for rule in RULE_LABELS}
    for flag in flags:
        counts[flag.rule] = counts.get(flag.rule, 0) + 1
    empty = visit_count == 0
    hint = None
    if empty:
        hint = (
            "No visits in this database yet. Load the sample files with "
            "service-tracker run --visits data/visits.csv --stock data/stock.csv "
            f"--settings data/settings.json --db {db_path} and refresh."
        )
    return {
        "db_path": db_path,
        "empty": empty,
        "hint": hint,
        "settings": {
            "repeat_failure_count": settings.repeat_failure_count,
            "repeat_failure_window_days": settings.repeat_failure_window_days,
        },
        "counts": counts,
        "flags": [flag_payload(flag) for flag in flags],
        "stock": stock,
    }


def history(db_path: str, serial: str) -> dict:
    serial = serial.strip().upper()
    with closing(open_db(db_path)) as conn:
        rows = history_for_serial(conn, serial)
    return {
        "serial": serial,
        "rows": rows,
        "text": format_history(serial, rows),
    }


def part(db_path: str, part_number: str) -> dict:
    part_number = part_number.strip().upper()
    with closing(open_db(db_path)) as conn:
        stock = conn.execute(
            """
            SELECT part_number, description, quantity_on_hand, reorder_level
            FROM stock
            WHERE part_number = ?
            """,
            (part_number,),
        ).fetchone()
        uses = conn.execute(
            """
            SELECT v.visit_id, v.serial_number, v.visit_date, v.technician, p.quantity
            FROM parts_used p
            JOIN visits v ON v.visit_id = p.visit_id
            WHERE p.part_number = ?
            ORDER BY v.visit_date, v.visit_id, p.id
            """,
            (part_number,),
        )
        uses = [dict(row) for row in uses]
    found = stock is not None
    payload = {
        "part_number": part_number,
        "found": found or bool(uses),
        "in_stock_list": found,
        "stock": stock_payload(dict(stock)) if found else None,
        "uses": uses,
    }
    if not payload["found"]:
        payload["text"] = f"No stock record or usage for {part_number}."
    elif found:
        row = payload["stock"]
        payload["text"] = (
            f"{part_number}  {row['description']}  "
            f"{row['quantity_on_hand']} on hand, reorder at {row['reorder_level']}"
        )
    else:
        payload["text"] = f"{part_number} is not in the stock list."
    return payload


def search(db_path: str, query: str) -> dict:
    """Find a machine by serial, or parts by number or description."""
    raw = query.strip()
    if not raw:
        return {"query": "", "machine": None, "parts": []}
    machine = history(db_path, raw)
    if not machine["rows"]:
        machine = None
    needle = raw.lower()
    with closing(open_db(db_path)) as conn:
        rows = conn.execute(
            """
            SELECT part_number
            FROM stock
            WHERE upper(part_number) = ?
               OR instr(lower(description), ?) > 0
            ORDER BY part_number
            """,
            (raw.upper(), needle),
        )
        numbers = [row["part_number"] for row in rows]
        if not numbers:
            used = conn.execute(
                """
                SELECT DISTINCT part_number
                FROM parts_used
                WHERE upper(part_number) = ?
                ORDER BY part_number
                """,
                (raw.upper(),),
            )
            numbers = [row["part_number"] for row in used]
    return {
        "query": raw,
        "machine": machine,
        "parts": [part(db_path, number) for number in numbers],
    }


def records(db_path: str) -> dict:
    """Every saved visit row and every stock row, for browsing."""
    with closing(open_db(db_path)) as conn:
        visit_count = conn.execute("SELECT COUNT(*) FROM visits").fetchone()[0]
        visits = conn.execute(
            """
            SELECT v.visit_id, v.serial_number, e.equipment_type, v.visit_date,
                   v.technician, v.problem_code, v.outcome, p.part_number, p.quantity
            FROM visits v
            JOIN equipment e ON e.serial_number = v.serial_number
            LEFT JOIN parts_used p ON p.visit_id = v.visit_id
            ORDER BY v.visit_date, v.visit_id, p.id
            """
        )
        stock = conn.execute(
            """
            SELECT part_number, description, quantity_on_hand, reorder_level
            FROM stock
            ORDER BY part_number
            """
        )
        visit_rows = [dict(row) for row in visits]
        stock_rows = [stock_payload(dict(row)) for row in stock]
    return {
        "visits": visit_rows,
        "stock": stock_rows,
        "counts": {
            "visits": visit_count,
            "visit_rows": len(visit_rows),
            "stock": len(stock_rows),
        },
    }


def current_report(db_path: str) -> str:
    settings = load_settings(resolve_settings_path())
    with closing(open_db(db_path)) as conn:
        visits = conn.execute("SELECT COUNT(*) FROM visits").fetchone()[0]
        serials = conn.execute(
            "SELECT COUNT(DISTINCT serial_number) FROM visits"
        ).fetchone()[0]
        flags = run_all_rules(conn, settings)
    summary = RunSummary(
        visits_loaded=visits,
        visits_saved=visits,
        duplicates=0,
        rejected=0,
        serials_checked=serials,
    )
    header = (
        "Current history report (saved database, not a CSV load).\n"
        f"Database: {db_path}\n\n"
    )
    return header + render_report(flags, summary)


def parse_guided(command: str) -> tuple[str, str | None]:
    text = command.strip()
    if text.startswith("service-tracker "):
        text = text[len("service-tracker ") :].strip()
    elif text in {"service-tracker", ""}:
        return "help", None

    parts = text.split()
    cmd = parts[0].lower()
    if cmd in {"help", "-h", "--help"}:
        return "help", None
    if cmd in {"version", "--version"}:
        return "version", None
    if cmd == "report":
        if len(parts) != 1:
            return "error", "usage: report"
        return "report", None
    if cmd == "history":
        if len(parts) != 2:
            return "error", "usage: history SERIAL"
        return "history", parts[1]
    if cmd == "run":
        return (
            "error",
            "run is not available in the UI. Load files with the "
            "service-tracker CLI, then refresh this page.",
        )
    return (
        "error",
        f"unknown command: {cmd}\nGuided commands: help, version, history SERIAL, report",
    )


def run_guided(db_path: str, command: str) -> tuple[bool, str]:
    kind, arg = parse_guided(command)
    if kind == "help":
        return True, GUIDED_HELP.strip()
    if kind == "version":
        return True, __version__
    if kind == "history":
        data = history(db_path, arg or "")
        return True, data["text"]
    if kind == "report":
        return True, current_report(db_path).rstrip()
    return False, arg or "unknown command"


class FrontendHandler(SimpleHTTPRequestHandler):
    db_path = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE), **kwargs)

    def log_message(self, format, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))

    def _send(self, status: int, body: dict | str, content_type: str = "application/json"):
        if isinstance(body, dict):
            payload = json.dumps(body).encode("utf-8")
        else:
            payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _send_error_json(self, status: int, message: str):
        self._send(status, {"ok": False, "error": message})

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/overview":
            try:
                self._send(200, overview(self.db_path))
            except SettingsError as error:
                self._send_error_json(400, str(error))
            except sqlite3.Error as error:
                self._send_error_json(500, f"database error: {error}")
            return
        if parsed.path == "/api/history":
            serial = parse_qs(parsed.query).get("serial", [""])[0]
            if not serial.strip():
                self._send_error_json(400, "usage: /api/history?serial=SERIAL")
                return
            try:
                self._send(200, history(self.db_path, serial))
            except sqlite3.Error as error:
                self._send_error_json(500, f"database error: {error}")
            return
        if parsed.path == "/api/part":
            part_number = parse_qs(parsed.query).get("part", [""])[0]
            if not part_number.strip():
                self._send_error_json(400, "usage: /api/part?part=PART")
                return
            try:
                self._send(200, part(self.db_path, part_number))
            except sqlite3.Error as error:
                self._send_error_json(500, f"database error: {error}")
            return
        if parsed.path == "/api/search":
            query = parse_qs(parsed.query).get("q", [""])[0]
            if not query.strip():
                self._send_error_json(400, "usage: /api/search?q=QUERY")
                return
            try:
                self._send(200, search(self.db_path, query))
            except sqlite3.Error as error:
                self._send_error_json(500, f"database error: {error}")
            return
        if parsed.path == "/api/records":
            try:
                self._send(200, records(self.db_path))
            except sqlite3.Error as error:
                self._send_error_json(500, f"database error: {error}")
            return
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/guided":
            self._send_error_json(404, "not found")
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._send_error_json(400, "body must be JSON")
            return
        command = payload.get("command", "")
        if not isinstance(command, str):
            self._send_error_json(400, "command must be a string")
            return
        try:
            ok, output = run_guided(self.db_path, command)
        except SettingsError as error:
            self._send_error_json(400, str(error))
            return
        except sqlite3.Error as error:
            self._send_error_json(500, f"database error: {error}")
            return
        self._send(200 if ok else 400, {"ok": ok, "output": output})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Serve the Service Visit Tracker Owner / Technical UI.",
    )
    parser.add_argument(
        "--db",
        metavar="PATH",
        help="SQLite database file. Overrides SERVICE_DB_PATH.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="bind address")
    parser.add_argument("--port", type=int, default=8765, help="bind port")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db_path = resolve_db_path(args.db)
    FrontendHandler.db_path = db_path
    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer((args.host, args.port), FrontendHandler)
    print(f"Service Visit Tracker UI  http://{args.host}:{args.port}", flush=True)
    print(f"Database  {db_path}", flush=True)
    print("Guided commands only. Load CSVs with service-tracker run.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
