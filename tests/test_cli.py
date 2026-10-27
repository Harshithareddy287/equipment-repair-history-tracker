"""The command line connects the loader, database, rules, and report."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from service_tracker import __version__
from service_tracker.cli import main
from service_tracker.db import connect, init_db, load_stock_records, save_visits
from service_tracker.loader import format_rejections, load_stock, load_visits
from service_tracker.report import RunSummary, render_report
from service_tracker.rules import run_all_rules
from service_tracker.settings import load_settings

DATA = Path(__file__).parent.parent / "data"
VISIT_HEADER = (
    "visit_id,serial_number,equipment_type,technician,visit_date,"
    "problem_code,part_number,quantity_used,outcome"
)
STOCK_HEADER = "part_number,description,quantity_on_hand,reorder_level"


def write_settings(path):
    path.write_text(
        json.dumps(
            {
                "repeat_failure_count": 3,
                "repeat_failure_window_days": 30,
                "part_number_pattern": "^P-\\d{4}$",
            }
        ),
        encoding="utf-8",
    )


def write_sample(tmp_path):
    """Two parts on one visit, one bad visit row, and one duplicate stock row."""
    visits = tmp_path / "visits.csv"
    visits.write_text(
        "\n".join(
            [
                VISIT_HEADER,
                "V-1,SN-1,switch,A. Okafor,2026-10-01,PWR,P-1001,1,fixed",
                "V-1,SN-1,switch,A. Okafor,2026-10-01,PWR,P-1002,1,fixed",
                "V-BAD,SN-1,switch,A. Okafor,2026-13-05,PWR,P-1001,1,fixed",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    stock = tmp_path / "stock.csv"
    stock.write_text(
        "\n".join(
            [
                STOCK_HEADER,
                "P-1001,PSU,10,2",
                "P-1002,Fan,10,2",
                "P-1001,duplicate,8,1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    settings = tmp_path / "settings.json"
    write_settings(settings)
    return visits, stock, settings


def run_args(visits, stock, settings, db=None):
    args = [
        "run",
        "--visits",
        str(visits),
        "--stock",
        str(stock),
        "--settings",
        str(settings),
    ]
    if db is not None:
        args.extend(["--db", str(db)])
    return args


def summary_value(output, label):
    prefix = f"{label}:"
    for line in output.splitlines():
        if line.startswith(prefix):
            return int(line.split(":", 1)[1].strip())
    raise AssertionError(f"{label} not found in output")


# --- arguments --------------------------------------------------------------


def test_version_prints_package_version(capsys):
    assert main(["--version"]) == 0
    captured = capsys.readouterr()
    assert captured.out == f"{__version__}\n"
    assert captured.err == ""


@pytest.mark.parametrize(
    "args",
    [
        ["run"],
        ["run", "--visits", "visits.csv", "--stock", "stock.csv"],
        ["run", "--visits", "visits.csv", "--settings", "settings.json"],
        ["run", "--stock", "stock.csv", "--settings", "settings.json"],
    ],
)
def test_run_requires_visits_stock_and_settings(capsys, args):
    with pytest.raises(SystemExit) as caught:
        main(args)
    assert caught.value.code == 2
    assert "required" in capsys.readouterr().err


def test_history_requires_a_serial_number(capsys):
    with pytest.raises(SystemExit) as caught:
        main(["history"])
    assert caught.value.code == 2
    assert "required" in capsys.readouterr().err


# --- expected input errors --------------------------------------------------


def test_missing_settings_file_prints_an_error(tmp_path, capsys):
    missing = tmp_path / "missing-settings.json"
    code = main(run_args(DATA / "visits.csv", DATA / "stock.csv", missing, tmp_path / "t.db"))
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err == f"settings error: {missing} not found\n"
    assert captured.out == ""
    assert not (tmp_path / "t.db").exists()


@pytest.mark.parametrize("which", ["visits", "stock"])
def test_missing_input_file_prints_an_error(tmp_path, capsys, which):
    visits = DATA / "visits.csv"
    stock = DATA / "stock.csv"
    if which == "visits":
        visits = tmp_path / "missing-visits.csv"
        missing = visits
    else:
        stock = tmp_path / "missing-stock.csv"
        missing = stock
    code = main(run_args(visits, stock, DATA / "settings.json", tmp_path / "t.db"))
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err == f"input error: {missing} not found\n"
    assert "Traceback" not in captured.err
    assert captured.out == ""


# --- history ----------------------------------------------------------------


def test_history_on_an_empty_database(tmp_path, capsys):
    serial = "SN-NONE"
    code = main(["history", serial, "--db", str(tmp_path / "empty.db")])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out == f"No history for {serial}.\n"
    assert captured.err == ""


def saved_sw4410(tmp_path, capsys):
    """Store one SW-4410 visit and clear the run command's output."""
    visits = tmp_path / "visits.csv"
    visits.write_text(
        "\n".join(
            [
                VISIT_HEADER,
                "V-0139,SW-4410,switch,A. Okafor,2026-10-02,PWR,P-1001,1,failed",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    stock = tmp_path / "stock.csv"
    stock.write_text(
        "\n".join([STOCK_HEADER, "P-1001,PSU,10,2"]) + "\n",
        encoding="utf-8",
    )
    settings = tmp_path / "settings.json"
    write_settings(settings)
    db = tmp_path / "service.db"
    assert main(run_args(visits, stock, settings, db)) == 0
    capsys.readouterr()
    return db


@pytest.mark.parametrize("typed", ["SW-4410", "sw-4410", "Sw-4410", "  sw-4410  "])
def test_history_finds_serial_regardless_of_case_and_space(tmp_path, capsys, typed):
    db = saved_sw4410(tmp_path, capsys)
    code = main(["history", typed, "--db", str(db)])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.err == ""
    assert captured.out.startswith("History for SW-4410\n")
    assert "V-0139" in captured.out
    assert "2026-10-02" in captured.out


def test_unknown_serial_uses_the_normalized_message(tmp_path, capsys):
    code = main(["history", "  no-such  ", "--db", str(tmp_path / "empty.db")])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out == "No history for NO-SUCH.\n"
    assert captured.err == ""


def sqlite_error_line(path):
    """The one stderr line the CLI prints when SQLite cannot open `path`."""
    try:
        sqlite3.connect(path)
    except sqlite3.Error as error:
        return f"database error: {error}\n"
    raise AssertionError(f"SQLite opened {path}")


@pytest.mark.parametrize("command", ["run", "history"])
def test_invalid_db_path_returns_1_without_a_traceback(tmp_path, capsys, command):
    bad = tmp_path / "missing-dir" / "service.db"
    if command == "run":
        visits, stock, settings = write_sample(tmp_path)
        args = run_args(visits, stock, settings, bad)
    else:
        args = ["history", "SW-4410", "--db", str(bad)]
    code = main(args)
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err == sqlite_error_line(bad)
    assert "Traceback" not in captured.err
    assert captured.err.count("\n") == 1


def test_bad_service_db_path_returns_1(tmp_path, monkeypatch, capsys):
    bad = tmp_path / "missing-dir" / "service.db"
    monkeypatch.setenv("SERVICE_DB_PATH", str(bad))
    code = main(["history", "sw-4410"])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err == sqlite_error_line(bad)
    assert captured.out == ""
    assert "Traceback" not in captured.err


def test_history_shows_visits_oldest_first(tmp_path, capsys):
    visits = tmp_path / "visits.csv"
    visits.write_text(
        "\n".join(
            [
                VISIT_HEADER,
                # Later visit is first in the file. History must not follow file order.
                "V-LATER,SN-9,switch,A. Okafor,2026-10-20,PWR,P-1001,1,failed",
                "V-EARLY,SN-9,switch,B. Lindqvist,2026-10-01,FAN,P-1002,2,fixed",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    stock = tmp_path / "stock.csv"
    stock.write_text(
        "\n".join([STOCK_HEADER, "P-1001,PSU,10,2", "P-1002,Fan,10,2"]) + "\n",
        encoding="utf-8",
    )
    settings = tmp_path / "settings.json"
    write_settings(settings)
    db = tmp_path / "history.db"
    assert main(run_args(visits, stock, settings, db)) == 0
    capsys.readouterr()

    code = main(["history", "SN-9", "--db", str(db)])
    captured = capsys.readouterr()
    assert code == 0
    output = captured.out
    assert output.index("V-EARLY") < output.index("V-LATER")
    assert output.index("2026-10-01") < output.index("2026-10-20")
    assert "B. Lindqvist" in output
    assert "P-1002 x2" in output
    assert "Service Visit Report" not in output


# --- run --------------------------------------------------------------------


def test_run_with_synthetic_data_returns_0(tmp_path, capsys):
    code = main(
        run_args(DATA / "visits.csv", DATA / "stock.csv", DATA / "settings.json", tmp_path / "t.db")
    )
    captured = capsys.readouterr()
    assert code == 0
    assert captured.err == ""
    assert "Service Visit Report" in captured.out


def test_run_prints_rejected_rows(tmp_path, capsys):
    code = main(
        run_args(DATA / "visits.csv", DATA / "stock.csv", DATA / "settings.json", tmp_path / "t.db")
    )
    assert code == 0
    output = capsys.readouterr().out
    assert "rows rejected:" in output
    assert "serial_number is missing" in output


def test_run_prints_the_report_from_the_report_module(tmp_path, capsys):
    db = tmp_path / "t.db"
    code = main(run_args(DATA / "visits.csv", DATA / "stock.csv", DATA / "settings.json", db))
    output = capsys.readouterr().out
    report = _report_from_library(tmp_path / "direct.db")
    assert code == 0
    assert report in output


def test_warning_flags_do_not_change_the_exit_code(tmp_path, capsys):
    code = main(
        run_args(DATA / "visits.csv", DATA / "stock.csv", DATA / "settings.json", tmp_path / "t.db")
    )
    output = capsys.readouterr().out
    assert code == 0
    assert "Repeat failures" in output
    assert "Low stock" in output
    assert "Stock shortfalls" in output


def test_db_argument_overrides_service_db_path(tmp_path, monkeypatch, capsys):
    env_db = tmp_path / "from-env.db"
    flag_db = tmp_path / "from-flag.db"
    monkeypatch.setenv("SERVICE_DB_PATH", str(env_db))
    visits, stock, settings = write_sample(tmp_path)
    code = main(run_args(visits, stock, settings, flag_db))
    assert code == 0
    assert flag_db.exists()
    assert not env_db.exists()
    capsys.readouterr()

    assert main(["history", "SN-1", "--db", str(flag_db)]) == 0
    assert "V-1" in capsys.readouterr().out


def test_service_db_path_is_used_when_db_is_omitted(tmp_path, monkeypatch, capsys):
    env_db = tmp_path / "from-env.db"
    monkeypatch.setenv("SERVICE_DB_PATH", str(env_db))
    visits, stock, settings = write_sample(tmp_path)
    assert main(run_args(visits, stock, settings)) == 0
    assert env_db.exists()
    capsys.readouterr()

    code = main(["history", "SN-1"])
    output = capsys.readouterr().out
    assert code == 0
    assert "V-1" in output
    assert output.index("P-1001 x1") < output.index("P-1002 x1")


def test_summary_counts_are_calculated_from_the_run(tmp_path, capsys):
    visits, stock, settings = write_sample(tmp_path)
    db = tmp_path / "t.db"
    assert main(run_args(visits, stock, settings, db)) == 0
    first = capsys.readouterr().out

    loaded_settings = load_settings(settings)
    stock_rows, stock_rej = load_stock(stock)
    visit_rows, visit_rej = load_visits(visits, loaded_settings.part_number_pattern)
    with closing(connect(tmp_path / "check.db")) as conn:
        init_db(conn)
        load_stock_records(conn, stock_rows)
        result = save_visits(conn, visit_rows)

    assert summary_value(first, "Visits loaded") == len({r.visit_id for r in visit_rows})
    assert summary_value(first, "Visits saved") == result.saved
    assert summary_value(first, "Duplicates") == len(result.duplicates)
    assert summary_value(first, "Rejected") == len(stock_rej) + len(visit_rej)
    assert summary_value(first, "Serials checked") == len({r.serial_number for r in visit_rows})

    assert main(run_args(visits, stock, settings, db)) == 0
    second = capsys.readouterr().out
    assert summary_value(second, "Visits loaded") == summary_value(first, "Visits loaded")
    assert summary_value(second, "Visits saved") == 0
    assert summary_value(second, "Duplicates") == result.saved
    assert summary_value(second, "Rejected") == len(stock_rej) + len(visit_rej)


def test_visits_loaded_counts_distinct_visit_ids(tmp_path, capsys):
    visits, stock, settings = write_sample(tmp_path)
    assert main(run_args(visits, stock, settings, tmp_path / "t.db")) == 0
    output = capsys.readouterr().out

    loaded_settings = load_settings(settings)
    visit_rows, _rejections = load_visits(visits, loaded_settings.part_number_pattern)
    distinct = len({r.visit_id for r in visit_rows})
    assert len(visit_rows) > distinct
    assert summary_value(output, "Visits loaded") == distinct
    assert summary_value(output, "Visits loaded") != len(visit_rows)


def test_cli_matches_loader_database_rules_and_report(tmp_path, capsys):
    db = tmp_path / "cli.db"
    code = main(run_args(DATA / "visits.csv", DATA / "stock.csv", DATA / "settings.json", db))
    output = capsys.readouterr().out

    settings = load_settings(DATA / "settings.json")
    _stock, stock_rej = load_stock(DATA / "stock.csv")
    _rows, visit_rej = load_visits(DATA / "visits.csv", settings.part_number_pattern)
    rejection_text = format_rejections([*stock_rej, *visit_rej])
    report = _report_from_library(tmp_path / "direct.db")

    assert code == 0
    assert rejection_text in output
    assert report in output
    assert output.index(rejection_text) < output.index("Service Visit Report")


def _report_from_library(db_path):
    """What the existing modules produce for the committed sample files."""
    settings = load_settings(DATA / "settings.json")
    stock, stock_rej = load_stock(DATA / "stock.csv")
    rows, visit_rej = load_visits(DATA / "visits.csv", settings.part_number_pattern)
    with closing(connect(db_path)) as conn:
        init_db(conn)
        load_stock_records(conn, stock)
        result = save_visits(conn, rows)
        flags = run_all_rules(conn, settings)
    summary = RunSummary(
        visits_loaded=len({r.visit_id for r in rows}),
        visits_saved=result.saved,
        duplicates=len(result.duplicates),
        rejected=len(stock_rej) + len(visit_rej),
        serials_checked=len({r.serial_number for r in rows}),
    )
    return render_report(flags, summary)
