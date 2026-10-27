# Changelog

## [Unreleased]

## [1.1.0]

### Added

- Unknown part rule. A part used on a visit that is not in stock is flagged. No database tables change, so Release 1.0.0 can still open the history.

## [1.0.0] - 2026-10-28

### Added

- Shared data classes `ServiceVisit`, `StockRecord` and `Rejection` in `service_tracker/models.py` (TEA-10).
- `load_settings` in `service_tracker/settings.py`, which reads `data/settings.json` and raises `SettingsError` with a clear message (TEA-10).
- `scripts/generate_data.py`, which writes repeatable synthetic `visits.csv`, `stock.csv` and `settings.json` with every demo case planted, plus `visits_unknown_parts.csv` behind `--with-unknown-parts`. Seed 42 output is committed in `data/` (TEA-9).
- `load_visits`, `load_stock` and `format_rejections` in `service_tracker/loader.py`. Bad rows become `Rejection`s with a line number and reason; a missing file or column raises `InputFileError` (TEA-11).
