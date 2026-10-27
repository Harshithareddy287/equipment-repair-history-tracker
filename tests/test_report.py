"""The service-manager report formats flags and a run summary."""

from datetime import date

from service_tracker.report import RunSummary, render_report
from service_tracker.rules.base import Flag


def make_summary(
    visits_loaded=4,
    visits_saved=3,
    duplicates=1,
    rejected=0,
    serials_checked=2,
):
    return RunSummary(
        visits_loaded=visits_loaded,
        visits_saved=visits_saved,
        duplicates=duplicates,
        rejected=rejected,
        serials_checked=serials_checked,
    )


def make_flag(
    rule,
    message,
    serial_number=None,
    part_number=None,
    visit_dates=None,
    quantity=None,
):
    return Flag(
        rule=rule,
        serial_number=serial_number,
        part_number=part_number,
        visit_dates=[] if visit_dates is None else visit_dates,
        quantity=quantity,
        message=message,
    )


def test_summary_statistics_come_from_the_summary():
    text = render_report([], make_summary(40, 36, 1, 3, 15))
    assert text.startswith("Service Visit Report\n")
    assert "Visits loaded:    40" in text
    assert "Visits saved:     36" in text
    assert "Duplicates:       1" in text
    assert "Rejected:         3" in text
    assert "Serials checked:  15" in text


def test_flags_are_grouped_under_their_headings():
    flags = [
        make_flag("repeat_failure", "repeat message", serial_number="SN-1"),
        make_flag("low_stock", "low message", part_number="P-1001", quantity=2),
        make_flag("shortfall", "short message", part_number="P-2002", quantity=-2),
    ]
    text = render_report(flags, make_summary())
    repeat_at = text.index("Repeat failures")
    low_at = text.index("Low stock")
    short_at = text.index("Stock shortfalls")
    assert repeat_at < text.index("repeat message") < low_at
    assert low_at < text.index("low message") < short_at
    assert short_at < text.index("short message")


def test_section_order_ignores_input_order():
    flags = [
        make_flag("shortfall", "short message", part_number="P-2002", quantity=-1),
        make_flag("low_stock", "low message", part_number="P-1001", quantity=1),
        make_flag("repeat_failure", "repeat message", serial_number="SN-1"),
    ]
    text = render_report(flags, make_summary())
    assert text.index("Repeat failures") < text.index("Low stock") < text.index(
        "Stock shortfalls"
    )


def test_multiple_flags_of_the_same_type_stay_in_one_section():
    flags = [
        make_flag("low_stock", "first part", part_number="P-1001", quantity=1),
        make_flag("low_stock", "second part", part_number="P-1002", quantity=0),
    ]
    text = render_report(flags, make_summary())
    assert text.count("Low stock") == 1
    low_at = text.index("Low stock")
    assert low_at < text.index("first part") < text.index("second part")


def test_visit_dates_are_formatted_as_iso():
    flag = make_flag(
        "repeat_failure",
        "repeat message",
        serial_number="SN-1",
        visit_dates=[date(2026, 1, 1), date(2026, 1, 5), date(2026, 1, 20)],
    )
    text = render_report([flag], make_summary())
    assert "  Visit dates:    2026-01-01, 2026-01-05, 2026-01-20" in text


def test_serial_number_is_displayed():
    flag = make_flag("repeat_failure", "repeat message", serial_number="SN-100")
    text = render_report([flag], make_summary())
    assert "  Serial number:  SN-100" in text


def test_part_number_is_displayed():
    flag = make_flag("low_stock", "low message", part_number="P-7001", quantity=2)
    text = render_report([flag], make_summary())
    assert "  Part number:    P-7001" in text


def test_quantity_includes_zero_and_negative_values():
    flags = [
        make_flag("low_stock", "zero on hand", part_number="P-1001", quantity=0),
        make_flag("shortfall", "negative on hand", part_number="P-1002", quantity=-2),
    ]
    text = render_report(flags, make_summary())
    assert "  Quantity:       0" in text
    assert "  Quantity:       -2" in text


def test_messages_are_preserved():
    message = "SN-100: 4 visits in 19 days (limit 3 in 30)"
    flag = make_flag("repeat_failure", message, serial_number="SN-100")
    text = render_report([flag], make_summary())
    assert message in text
    assert "  Message:        " + message in text


def test_no_issues_message_uses_summary_counts():
    text = render_report([], make_summary(visits_loaded=12, serials_checked=4))
    assert "No issues found. 12 visits across 4 serial numbers checked." in text
    assert "Repeat failures" not in text
    assert "Low stock" not in text
    assert "Stock shortfalls" not in text


def test_changing_summary_values_changes_output():
    flags = [make_flag("low_stock", "same message", part_number="P-1001", quantity=2)]
    first = render_report(flags, make_summary(visits_loaded=1, serials_checked=1))
    second = render_report(flags, make_summary(visits_loaded=9, serials_checked=4))
    assert "Visits loaded:    1" in first
    assert "Visits loaded:    9" in second
    assert "Serials checked:  1" in first
    assert "Serials checked:  4" in second
    assert "same message" in first
    assert "same message" in second


def test_unknown_part_heading_is_unknown_parts():
    flags = [
        make_flag("repeat_failure", "repeat message", serial_number="SN-1"),
        make_flag("low_stock", "low message", part_number="P-1001", quantity=2),
        make_flag("shortfall", "short message", part_number="P-2002", quantity=-2),
        make_flag(
            "unknown_part",
            "P-9901 is not in stock",
            serial_number="SN-100",
            part_number="P-9901",
            visit_dates=[date(2026, 10, 1)],
            quantity=1,
        ),
    ]
    text = render_report(flags, make_summary())
    lines = text.splitlines()
    assert "Unknown parts" in lines
    assert lines.index("Repeat failures") < lines.index("Low stock")
    assert lines.index("Low stock") < lines.index("Stock shortfalls")
    assert lines.index("Stock shortfalls") < lines.index("Unknown parts")
    assert text.index("\nUnknown parts\n") < text.index("P-9901 is not in stock")


def test_unknown_rules_follow_the_required_groups_in_name_order():
    flags = [
        make_flag("zeta_check", "zeta message", part_number="P-9002"),
        make_flag("shortfall", "short message", part_number="P-1002", quantity=-1),
        make_flag("alpha_check", "alpha message", part_number="P-9001"),
        make_flag("repeat_failure", "repeat message", serial_number="SN-1"),
    ]
    text = render_report(flags, make_summary())
    short_at = text.index("Stock shortfalls")
    alpha_at = text.index("Alpha check")
    zeta_at = text.index("Zeta check")
    assert text.index("Repeat failures") < short_at < alpha_at < zeta_at
    assert alpha_at < text.index("alpha message") < zeta_at
    assert zeta_at < text.index("zeta message")


def test_footer_is_included_with_and_without_flags():
    empty = render_report([], make_summary())
    flagged = render_report(
        [make_flag("low_stock", "low message", part_number="P-1001", quantity=2)],
        make_summary(),
    )
    for text in (empty, flagged):
        assert "The tool only flags and reports issues." in text
        assert "It does not order parts, schedule repairs," in text
        assert "or decide whether equipment should be replaced." in text
        assert text.endswith(
            "or decide whether equipment should be replaced.\n"
        )


def test_missing_optional_fields_are_omitted():
    flag = make_flag("low_stock", "part only", part_number="P-1001", quantity=2)
    text = render_report([flag], make_summary())
    assert "None" not in text
    assert "Serial number:" not in text
    assert "Visit dates:" not in text

    bare = make_flag("note", "message only")
    bare_text = render_report([bare], make_summary())
    assert "None" not in bare_text
    assert "Serial number:" not in bare_text
    assert "Part number:" not in bare_text
    assert "Visit dates:" not in bare_text
    assert "Quantity:" not in bare_text
    assert "message only" in bare_text


def test_render_report_returns_a_string_without_printing(capsys):
    text = render_report([], make_summary())
    assert isinstance(text, str)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_inputs_are_not_modified():
    dates = [date(2026, 4, 1), date(2026, 4, 5)]
    flags = [
        make_flag("shortfall", "short message", part_number="P-1002", quantity=-1),
        make_flag(
            "repeat_failure",
            "repeat message",
            serial_number="SN-1",
            visit_dates=dates,
        ),
    ]
    summary = make_summary(7, 6, 1, 0, 3)
    before_flags = [(flag.rule, flag.message, list(flag.visit_dates)) for flag in flags]
    before_summary = (
        summary.visits_loaded,
        summary.visits_saved,
        summary.duplicates,
        summary.rejected,
        summary.serials_checked,
    )
    render_report(flags, summary)
    assert [(flag.rule, flag.message, list(flag.visit_dates)) for flag in flags] == before_flags
    assert flags[1].visit_dates is dates
    assert (
        summary.visits_loaded,
        summary.visits_saved,
        summary.duplicates,
        summary.rejected,
        summary.serials_checked,
    ) == before_summary
