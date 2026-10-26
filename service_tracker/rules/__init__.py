"""Rule registry. A new rule is one subclass plus one entry in RULES."""

from service_tracker.rules.base import Flag, FlagRule
from service_tracker.rules.low_stock import LowStockRule
from service_tracker.rules.repeat_failure import RepeatFailureRule
from service_tracker.rules.shortfall import ShortfallRule

# Registration order is the order flags are returned in.
RULES: list[FlagRule] = [
    RepeatFailureRule(),
    LowStockRule(),
    ShortfallRule(),
]


def run_all_rules(conn, settings) -> list[Flag]:
    """Run every rule and return every flag. Keep going after a hit."""
    flags: list[Flag] = []
    for rule in RULES:
        flags.extend(rule.evaluate(conn, settings))
    return flags
