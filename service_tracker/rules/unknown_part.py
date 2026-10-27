"""Flag a part used on a visit when that part is not in stock.

unknown_parts already returns those rows, one per parts_used line, oldest
visit first. A part that is in stock is absent from that list. This rule
does not use settings.
"""

from datetime import date

from service_tracker.db import unknown_parts
from service_tracker.rules.base import Flag, FlagRule


class UnknownPartRule(FlagRule):
    """One flag per parts_used row returned by unknown_parts."""

    name = "unknown_part"

    def evaluate(self, conn, settings) -> list[Flag]:
        """Flag every unknown part unknown_parts returns.

        settings is part of the FlagRule signature. The stock lookup is
        already done by that query. Flags stay in the query's order, so the
        same part used on two visits is two flags and the same row is never
        flagged twice.
        """
        flags = []
        for row in unknown_parts(conn):
            part_number = row["part_number"]
            flags.append(
                Flag(
                    rule=self.name,
                    serial_number=row["serial_number"],
                    part_number=part_number,
                    visit_dates=[date.fromisoformat(row["visit_date"])],
                    quantity=row["quantity"],
                    message=f"{part_number} is not in stock",
                )
            )
        return flags
