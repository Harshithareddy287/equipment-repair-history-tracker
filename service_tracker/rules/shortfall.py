"""Flag a part whose quantity on hand is below zero.

The stock table stores quantity_on_hand as INTEGER NOT NULL and does not
check that the number is zero or more. A negative count is a shortfall.
Zero is not. This rule only reads stock. It does not change it.
"""

from service_tracker.rules.base import Flag, FlagRule


def _stock_rows(conn):
    """Every part, in part-number order. quantity_on_hand is an int."""
    return conn.execute(
        """
        SELECT part_number, quantity_on_hand
        FROM stock
        ORDER BY part_number
        """
    ).fetchall()


class ShortfallRule(FlagRule):
    """One flag per part with a negative quantity on hand."""

    name = "shortfall"

    def evaluate(self, conn, settings) -> list[Flag]:
        """Flag parts whose quantity on hand is below zero.

        settings is part of the FlagRule signature. This rule compares
        quantity_on_hand with zero.
        """
        flags = []
        for row in _stock_rows(conn):
            on_hand = row["quantity_on_hand"]
            if on_hand >= 0:
                continue
            part_number = row["part_number"]
            flags.append(
                Flag(
                    rule=self.name,
                    serial_number=None,
                    part_number=part_number,
                    visit_dates=[],
                    quantity=on_hand,
                    message=f"{part_number} has {on_hand} on hand, which is below zero",
                )
            )
        return flags
