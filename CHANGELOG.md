# Changelog

## [Unreleased]

### Added

- Shared data classes `ServiceVisit`, `StockRecord` and `Rejection` in `service_tracker/models.py` (TEA-10).
- `load_settings` in `service_tracker/settings.py`, which reads `data/settings.json` and raises `SettingsError` with a clear message (TEA-10).
