# Changelog

## [Unreleased]

### Added

- Shared data classes `ServiceVisit`, `StockRecord` and `Rejection` in `service_tracker/models.py` (TEA-10).
- `load_settings` in `service_tracker/settings.py`, which reads `data/settings.json` and raises `SettingsError` with a clear message (TEA-10).
- `scripts/generate_data.py`, which writes repeatable synthetic `visits.csv`, `stock.csv` and `settings.json` with every demo case planted, plus `visits_unknown_parts.csv` behind `--with-unknown-parts`. Seed 42 output is committed in `data/` (TEA-9).
