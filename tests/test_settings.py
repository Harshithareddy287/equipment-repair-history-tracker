"""load_settings reads data/settings.json and explains every bad file clearly."""

import json
from pathlib import Path

import pytest

from service_tracker.settings import Settings, SettingsError, load_settings

VALID = {
    "repeat_failure_count": 3,
    "repeat_failure_window_days": 30,
    "part_number_pattern": "^P-\\d{4}$",
}


def write(tmp_path, data):
    path = tmp_path / "settings.json"
    path.write_text(data if isinstance(data, str) else json.dumps(data))
    return path


def test_valid_file_loads(tmp_path):
    assert load_settings(write(tmp_path, VALID)) == Settings(3, 30, "^P-\\d{4}$")


def test_repo_settings_file_loads():
    path = Path(__file__).parent.parent / "data" / "settings.json"
    assert load_settings(path) == Settings(3, 30, "^P-\\d{4}$")


def test_missing_file(tmp_path):
    path = tmp_path / "nope.json"
    with pytest.raises(SettingsError) as e:
        load_settings(path)
    assert str(e.value) == f"settings error: {path} not found"


def test_invalid_json_reports_line(tmp_path):
    path = write(tmp_path, '{\n  "repeat_failure_count": 3,\n  oops\n}')
    with pytest.raises(SettingsError) as e:
        load_settings(path)
    assert str(e.value) == f"settings error: {path} is not valid JSON (line 3)"


def test_top_level_must_be_an_object(tmp_path):
    with pytest.raises(SettingsError, match="must contain a JSON object"):
        load_settings(write(tmp_path, "[]"))


@pytest.mark.parametrize("key", list(VALID))
def test_missing_key(tmp_path, key):
    data = {k: v for k, v in VALID.items() if k != key}
    with pytest.raises(SettingsError) as e:
        load_settings(write(tmp_path, data))
    assert str(e.value) == f'settings error: missing key "{key}"'


@pytest.mark.parametrize("key", ["repeat_failure_count", "repeat_failure_window_days"])
@pytest.mark.parametrize("value", ["3", 0, -1, True, 2.5])
def test_non_positive_whole_number_rejected(tmp_path, key, value):
    with pytest.raises(SettingsError) as e:
        load_settings(write(tmp_path, {**VALID, key: value}))
    assert str(e.value) == f'settings error: "{key}" must be a positive whole number'


@pytest.mark.parametrize("pattern", ["^P-(\\d{4}$", 42])
def test_bad_regex(tmp_path, pattern):
    with pytest.raises(SettingsError) as e:
        load_settings(write(tmp_path, {**VALID, "part_number_pattern": pattern}))
    assert str(e.value) == (
        "settings error: part_number_pattern is not a valid regular expression"
    )


def test_unknown_key_ignored(tmp_path):
    settings = load_settings(write(tmp_path, {**VALID, "unknown_part_rule": True}))
    assert settings == Settings(3, 30, "^P-\\d{4}$")
