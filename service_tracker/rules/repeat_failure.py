"""Flag a serial number that is visited too often inside the configured window.

The limits are settings.repeat_failure_count and
settings.repeat_failure_window_days. Nothing in this file is a fixed
threshold, serial number, or date.

all_visits(conn) is not in service_tracker.db on this branch. The visits
table is the table that function will read, so evaluate loads it here.
visit_date is ISO text on a sqlite3.Row.
"""

from collections import defaultdict
from datetime import date

from service_tracker.rules.base import Flag, FlagRule


def _visit_rows(conn):
    """Every saved visit, in serial-number order."""
    return conn.execute(
        """
        SELECT serial_number, visit_date
        FROM visits
        ORDER BY serial_number, visit_date, visit_id
        """
    ).fetchall()


def _first_qualifying_window(dates, count, window_days):
    """Earliest `count` dates whose first and last are within the window.

    dates is already sorted. The span is the number of days from the first
    date in the group to the last. A span equal to window_days still counts.
    """
    if count < 1 or len(dates) < count:
        return None
    for start in range(len(dates) - count + 1):
        end = start + count - 1
        span_days = (dates[end] - dates[start]).days
        if span_days <= window_days:
            return dates[start : end + 1]
    return None


class RepeatFailureRule(FlagRule):
    """One flag per serial number that has enough visits in the window."""

    name = "repeat_failure"

    def evaluate(self, conn, settings) -> list[Flag]:
        by_serial = defaultdict(list)
        for row in _visit_rows(conn):
            visit_day = date.fromisoformat(row["visit_date"])
            by_serial[row["serial_number"]].append(visit_day)

        flags = []
        for serial_number, visit_dates in by_serial.items():
            window = _first_qualifying_window(
                sorted(visit_dates),
                settings.repeat_failure_count,
                settings.repeat_failure_window_days,
            )
            if window is None:
                continue
            flags.append(
                Flag(
                    rule=self.name,
                    serial_number=serial_number,
                    part_number=None,
                    visit_dates=window,
                    quantity=None,
                    message=(
                        f"{serial_number} has {len(window)} visits from "
                        f"{window[0].isoformat()} to {window[-1].isoformat()}"
                    ),
                )
            )
        return flags
