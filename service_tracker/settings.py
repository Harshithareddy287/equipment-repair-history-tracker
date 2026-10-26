"""Load limits from data/settings.json so they change without a code change."""

import json
import re
from dataclasses import dataclass

INT_KEYS = ("repeat_failure_count", "repeat_failure_window_days")


@dataclass(frozen=True)
class Settings:
    repeat_failure_count: int
    repeat_failure_window_days: int
    part_number_pattern: str


class SettingsError(Exception):
    """The settings file is missing, malformed, or holds a bad value."""


def load_settings(path) -> Settings:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise SettingsError(f"settings error: {path} not found") from None
    except json.JSONDecodeError as e:
        raise SettingsError(
            f"settings error: {path} is not valid JSON (line {e.lineno})"
        ) from None

    if not isinstance(data, dict):
        raise SettingsError(f"settings error: {path} must contain a JSON object")

    for key in (*INT_KEYS, "part_number_pattern"):
        if key not in data:
            raise SettingsError(f'settings error: missing key "{key}"')
        if key in INT_KEYS:
            value = data[key]
            # bool is a subclass of int, so true would otherwise pass as 1.
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise SettingsError(
                    f'settings error: "{key}" must be a positive whole number'
                )

    pattern = data["part_number_pattern"]
    try:
        if not isinstance(pattern, str):
            raise TypeError
        re.compile(pattern)
    except (re.error, TypeError):
        raise SettingsError(
            "settings error: part_number_pattern is not a valid regular expression"
        ) from None

    # Unknown keys are ignored so an older release can read a newer file.
    return Settings(
        repeat_failure_count=data["repeat_failure_count"],
        repeat_failure_window_days=data["repeat_failure_window_days"],
        part_number_pattern=pattern,
    )
