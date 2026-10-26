"""The shared Flag value and the FlagRule parent every rule inherits from."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Flag:
    """One problem found by a rule.

    serial_number is set for a visit rule and part_number for a stock rule.
    The other one stays None. visit_dates is empty when the rule is not about
    visits, and quantity stays None when the rule is not about stock.
    """

    rule: str
    serial_number: str | None
    part_number: str | None
    visit_dates: list[date]
    quantity: int | None
    message: str


class FlagRule(ABC):
    """A named check over the database.

    Subclasses set name and replace evaluate. The caller owns conn: a rule
    must not open it or close it.
    """

    name: str

    @abstractmethod
    def evaluate(self, conn, settings) -> list[Flag]:
        """Return every Flag this rule finds, or an empty list."""
        raise NotImplementedError
