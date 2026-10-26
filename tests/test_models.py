"""The shared data classes build with the agreed fields and cannot be changed."""

import dataclasses
from datetime import date

import pytest

from service_tracker.models import OUTCOMES, Rejection, ServiceVisit, StockRecord


def make_visit():
    return ServiceVisit(
        visit_id="V-0101",
        serial_number="SW-4410",
        equipment_type="switch",
        technician="T. Rivera",
        visit_date=date(2026, 3, 4),
        problem_code="PWR",
        part_number="P-2031",
        quantity_used=2,
        outcome="fixed",
    )


def make_stock():
    return StockRecord(
        part_number="P-2031",
        description="Power supply",
        quantity_on_hand=2,
        reorder_level=5,
    )


def make_rejection():
    return Rejection(
        source="visits",
        line_number=7,
        raw={"visit_id": "V-0107", "serial_number": ""},
        reason="serial_number is empty",
    )


def test_service_visit_holds_its_fields():
    visit = make_visit()
    assert visit.visit_date == date(2026, 3, 4)
    assert visit.quantity_used == 2
    assert visit.outcome in OUTCOMES


def test_stock_record_holds_its_fields():
    stock = make_stock()
    assert stock.part_number == "P-2031"
    assert (stock.quantity_on_hand, stock.reorder_level) == (2, 5)


def test_rejection_holds_its_fields():
    rejection = make_rejection()
    assert rejection.source == "visits"
    assert rejection.line_number == 7
    assert rejection.raw["visit_id"] == "V-0107"


def test_outcomes_match_the_readme():
    assert OUTCOMES == {"fixed", "failed", "replaced_part", "escalated"}


@pytest.mark.parametrize(
    "instance, field",
    [
        (make_visit(), "outcome"),
        (make_stock(), "quantity_on_hand"),
        (make_rejection(), "reason"),
    ],
)
def test_assigning_a_field_raises(instance, field):
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(instance, field, "changed")
