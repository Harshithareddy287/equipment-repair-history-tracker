"""Format the service-manager report from flags and a run summary.

render_report only builds text. It does not read the database, the CSV
files, or the settings file, and it does not change the objects it is given.
"""

from dataclasses import dataclass

from service_tracker.rules.base import Flag

TITLE = "Service Visit Report"

FOOTER = (
    "The tool only flags and reports issues.\n"
    "It does not order parts, schedule repairs,\n"
    "or decide whether equipment should be replaced."
)

# These groups are printed first, in this order. Any other rule name
# follows, sorted by that name.
_KNOWN_SECTIONS = (
    ("repeat_failure", "Repeat failures"),
    ("low_stock", "Low stock"),
    ("shortfall", "Stock shortfalls"),
    ("unknown_part", "Unknown parts"),
)


@dataclass
class RunSummary:
    """Counts from one run of the tracker. The report prints these as given."""

    visits_loaded: int
    visits_saved: int
    duplicates: int
    rejected: int
    serials_checked: int


def render_report(flags: list[Flag], summary: RunSummary) -> str:
    """Return the full report as one string."""
    lines = [TITLE, "", *_summary_lines(summary), ""]
    if flags:
        lines.extend(_flag_lines(flags))
    else:
        lines.append(
            f"No issues found. {summary.visits_loaded} visits across "
            f"{summary.serials_checked} serial numbers checked."
        )
    lines.extend(["", FOOTER])
    return "\n".join(lines) + "\n"


def _summary_lines(summary):
    rows = (
        ("Visits loaded", summary.visits_loaded),
        ("Visits saved", summary.visits_saved),
        ("Duplicates", summary.duplicates),
        ("Rejected", summary.rejected),
        ("Serials checked", summary.serials_checked),
    )
    return [f"{label + ':':<18}{value}" for label, value in rows]


def _flag_lines(flags):
    """Section headings and one block per flag, in the required order."""
    grouped = {}
    for flag in flags:
        grouped.setdefault(flag.rule, []).append(flag)

    sections = []
    shown = set()
    for rule, heading in _KNOWN_SECTIONS:
        if rule in grouped:
            shown.add(rule)
            sections.append((heading, grouped[rule]))
    for rule in sorted(grouped):
        if rule not in shown:
            sections.append((_heading(rule), grouped[rule]))

    lines = []
    for index, (heading, group) in enumerate(sections):
        if index:
            lines.append("")
        lines.append(heading)
        for flag_index, flag in enumerate(group):
            if flag_index:
                lines.append("")
            lines.extend(_one_flag(flag))
    return lines


def _heading(rule):
    """Turn an unlisted rule id such as zeta_check into a heading."""
    text = rule.replace("_", " ")
    if not text:
        return rule
    return text[0].upper() + text[1:]


def _one_flag(flag):
    """The lines for one flag. Skip a field that is None or empty."""
    lines = []
    if flag.serial_number:
        lines.append(_field("Serial number", flag.serial_number))
    if flag.part_number:
        lines.append(_field("Part number", flag.part_number))
    if flag.visit_dates:
        dates = ", ".join(day.isoformat() for day in flag.visit_dates)
        lines.append(_field("Visit dates", dates))
    if flag.quantity is not None:
        lines.append(_field("Quantity", flag.quantity))
    lines.append(_field("Message", flag.message))
    return lines


def _field(label, value):
    return f"  {label + ':':<16}{value}"
