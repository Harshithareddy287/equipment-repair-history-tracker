"""Flag a part whose quantity on hand is at or below its reorder level.

The comparison is the low-stock rule: quantity_on_hand <= reorder_level.
Both numbers come from the stock row. This rule does not use settings.

low_stock_parts(conn) is not in service_tracker.db on this branch. The stock
table is the table that function will read, so evaluate loads it here.
"""

from service_tracker.rules.base import Flag, FlagRule


def _stock_rows(conn):
    """Every part, in part-number order. quantity_on_hand is an int."""
    return conn.execute(
        """
        SELECT part_number, quantity_on_hand, reorder_level
        FROM stock
        ORDER BY part_number
        """
    ).fetchall()


class LowStockRule(FlagRule):
    """One flag per part at or below its own reorder level."""

    name = "low_stock"

    def evaluate(self, conn, settings) -> list[Flag]:
        """Flag parts at or below their reorder level.

        settings is part of the FlagRule signature. This rule reads each
        part's own reorder level instead.
        """
        flags = []
        for row in _stock_rows(conn):
            on_hand = row["quantity_on_hand"]
            reorder_level = row["reorder_level"]
            if on_hand > reorder_level:
                continue
            part_number = row["part_number"]
            flags.append(
                Flag(
                    rule=self.name,
                    serial_number=None,
                    part_number=part_number,
                    visit_dates=[],
                    quantity=on_hand,
                    message=(
                        f"{part_number} has {on_hand} on hand, "
                        f"at or below its reorder level of {reorder_level}"
                    ),
                )
            )
        return flags
