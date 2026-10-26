"""Flag a part whose quantity on hand is at or below its reorder level.

low_stock_parts already returns those parts, including a negative count.
Both numbers on the flag come from that row. This rule does not use settings.
"""

from service_tracker.db import low_stock_parts
from service_tracker.rules.base import Flag, FlagRule


class LowStockRule(FlagRule):
    """One flag per part returned by low_stock_parts."""

    name = "low_stock"

    def evaluate(self, conn, settings) -> list[Flag]:
        """Flag every part low_stock_parts returns.

        settings is part of the FlagRule signature. The reorder comparison
        is already done by that query.
        """
        flags = []
        for row in low_stock_parts(conn):
            on_hand = row["quantity_on_hand"]
            reorder_level = row["reorder_level"]
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
