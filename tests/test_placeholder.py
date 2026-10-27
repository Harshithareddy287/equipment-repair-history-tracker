"""Scaffold check so CI has a test to run before feature tests land."""

import service_tracker


def test_package_imports_and_reports_a_version():
    assert service_tracker.__version__ == "1.0.0"
