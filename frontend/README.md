# Frontend

Owner dashboard and guided Technical mode for the Service Visit Tracker.
The page reads the same SQLite file the CLI uses. It does not load CSV
files, and it does not change the `service_tracker` package.

Owner mode is for a non-technical viewer: flag counts, the rule those
flags used, stock at or under reorder level, and a lookup for a serial
or part name (for example Fan). Records mode lists every saved visit
and stock row. Technical mode is a guided terminal for `help`, `version`,
`history SERIAL`, and `report`. Free-form commands and `run` stay on
the real CLI so the UI cannot write a surprise load.

Use the View dropdown to switch modes. Dark mode is in the header and
is remembered for the next visit.

## Seed the database

From the repo root, with the package installed:

```bash
python -m pip install -e ".[dev]"
service-tracker run --visits data/visits.csv --stock data/stock.csv --settings data/settings.json --db demo.db
```

That is the same sample batch the presentation uses. `history SW-4410`
should then print three visits. `P-1180` is the shortfall part.

## Start the UI

```bash
python frontend/server.py --db demo.db
```

Open http://127.0.0.1:8765

If `--db` and `SERVICE_DB_PATH` are omitted, the server uses `demo.db`
when that file exists, otherwise `service.db` in the repo root.

```bash
python frontend/server.py --help
```

## Guided commands

In Technical mode, chips or the prompt accept:

- `help`
- `version`
- `history SW-4410`
- `report`

Anything else, including `run`, is rejected with a short hint. Load new
files with `service-tracker run`, then refresh the page.

## Tests

```bash
pytest tests/test_frontend.py -q
```

The tests seed a temporary database with the real sample files and check
overview counts, `SW-4410` history, `P-1180` part lookup, and the
guided whitelist.
