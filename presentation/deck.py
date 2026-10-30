"""Helpers for the interactive presentation in presentation/index.html.

The slides run short Python snippets against the real service_tracker
package. A snippet prints text as usual and calls the functions below to
add a chart or table to its output. The same module runs in the browser
(Pyodide) and in build_bundle.py, which records every snippet's output as a
fallback for when the browser cannot load Python.

Nothing in service_tracker imports this module.
"""

import contextlib
import io
import json
import os
import shutil
import sys
import traceback
from datetime import date

_visuals = []


# Visuals ---------------------------------------------------------------

def stats(items, tones=None):
    """A row of big numbers. items is {label: value}; tones is {label: tone}.

    A tone is "ok", "warn", "bad" or omitted.
    """
    tones = tones or {}
    _visuals.append({
        "kind": "stats",
        "items": [
            {"label": label, "value": value, "tone": tones.get(label)}
            for label, value in items.items()
        ],
    })


def table(rows, columns=None, title=None, highlight=None, limit=12):
    """A table of dict rows. highlight is {"column": name, "values": [...]}."""
    rows = [dict(r) for r in rows]
    columns = columns or (list(rows[0]) if rows else [])
    _visuals.append({
        "kind": "table",
        "title": title,
        "columns": columns,
        "rows": [[r.get(c) for c in columns] for r in rows[:limit]],
        "more": max(0, len(rows) - limit),
        "highlight": highlight,
    })


def bars(title, items, highlight=(), unit=""):
    """Horizontal bars. items is a list of (label, value) pairs."""
    _visuals.append({
        "kind": "bars",
        "title": title,
        "items": [{"label": str(k), "value": v} for k, v in items],
        "highlight": [str(h) for h in highlight],
        "unit": unit,
    })


def columns(title, items, highlight=()):
    """Vertical columns, for many short labels. items: (label, value) pairs."""
    _visuals.append({
        "kind": "columns",
        "title": title,
        "items": [{"label": str(k), "value": v} for k, v in items],
        "highlight": [str(h) for h in highlight],
    })


def compare(title, before, after, before_label="Before", after_label="After"):
    """Paired bars for the same keys, such as table row counts."""
    _visuals.append({
        "kind": "compare",
        "title": title,
        "labels": [before_label, after_label],
        "items": [
            {"label": key, "before": before.get(key, 0), "after": after.get(key, 0)}
            for key in after
        ],
    })


def stock(title, rows):
    """Stock levels. rows: dicts with part, before, after and reorder."""
    _visuals.append({"kind": "stock", "title": title, "rows": list(rows)})


def timeline(title, rows, start, end):
    """Visit dates per serial. rows: dicts with label, dates, window (or None)."""
    _visuals.append({
        "kind": "timeline",
        "title": title,
        "start": str(start),
        "end": str(end),
        "rows": [
            {
                "label": r["label"],
                "dates": [str(d) for d in r["dates"]],
                "window": [str(d) for d in r["window"]] if r.get("window") else None,
            }
            for r in rows
        ],
    })


def terminal(text, title=None):
    """Command output shown as a terminal window."""
    _visuals.append({"kind": "terminal", "title": title, "text": text})


# Workspace helpers -----------------------------------------------------

def fresh_path(name):
    """Delete a scratch file or folder so a snippet starts from nothing."""
    if os.path.isdir(name):
        shutil.rmtree(name)
    elif os.path.exists(name):
        os.remove(name)
    folder = os.path.dirname(name)
    if folder:
        os.makedirs(folder, exist_ok=True)
    return name


def forget_modules():
    """Drop imported tracker modules, like a container that starts again.

    Files on disk (the database) stay; Python state such as a rule added to
    RULES during an earlier snippet does not.
    """
    for name in list(sys.modules):
        if name == "service_tracker" or name.startswith("service_tracker."):
            del sys.modules[name]
        elif name == "generate_data":
            del sys.modules[name]


# Runner ----------------------------------------------------------------

def run_snippet(code, workdir):
    """Run one snippet in workdir and return its output as JSON text."""
    _visuals.clear()
    forget_modules()
    previous = os.getcwd()
    os.chdir(workdir)
    out = io.StringIO()
    ok = True
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            try:
                exec(compile(code, "<snippet>", "exec"), {"__name__": "__main__"})
            except SystemExit:
                pass
            except BaseException as error:  # shown to the audience, not raised
                ok = False
                lines = traceback.format_exception(error)
                # Keep the snippet's own frames and the error, drop this runner.
                keep = [lines[0]] + [
                    line for line in lines[1:]
                    if "deck.py" not in line and "exec(compile(" not in line
                ]
                out.write("".join(keep))
    finally:
        os.chdir(previous)
    return json.dumps(
        {"ok": ok, "stdout": out.getvalue(), "visuals": list(_visuals)},
        default=_jsonable,
    )


def _jsonable(value):
    if isinstance(value, date):
        return value.isoformat()
    return str(value)
