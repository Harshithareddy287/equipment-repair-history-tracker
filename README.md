# Service Visit Tracker

[![CI](https://github.com/Harshithareddy287/equipment-repair-history-tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/Harshithareddy287/equipment-repair-history-tracker/actions/workflows/ci.yml)

A command line tool for a service company that repairs servers and network equipment. Technicians log each visit and the parts they used. The tool keeps that history in one SQLite database and prints a report when the same equipment keeps failing or spare parts are running out. It flags and reports. It does not order parts, schedule a repair, or decide that equipment should be replaced.

Team: Natalie King, Julian Marchington, Shreyaa Lakshmivaragan, Harshitha Reddy Gundavarapu.

The decisions below are the shared contract. Change them only when the whole team agrees, and update this file in the same pull request.

## Shared decisions

### Visit CSV

Columns: `visit_id`, `serial_number`, `equipment_type`, `technician`, `visit_date`, `problem_code`, `part_number`, `quantity_used`, `outcome`.

Dates are ISO `YYYY-MM-DD`. One row is one part used. A visit that used two parts is two rows that share a `visit_id`.

Outcome values: `fixed`, `failed`, `replaced_part`, `escalated`.

### Stock CSV

Columns: `part_number`, `description`, `quantity_on_hand`, `reorder_level`.

Every customer, serial number, technician, and part in this project is synthetic. The generator is `scripts/generate_data.py`.

### Settings file

`settings.json`:

```json
{
  "repeat_failure_count": 3,
  "repeat_failure_window_days": 30,
  "part_number_pattern": "^P-\\d{4}$"
}
```

A manager changes the repeat-failure limit by editing this file. No code change is required.

### Definitions

| Name | Meaning | Example |
| --- | --- | --- |
| Bad record | A row that cannot be trusted. It is rejected while loading and is never saved. | Visit `V-0107` has an empty serial number. |
| Repeat failure | The same serial number has at least `repeat_failure_count` visits inside `repeat_failure_window_days`. | `SW-4410` has 3 visits inside 30 days. |
| Low stock | After usage is applied, `quantity_on_hand` is less than or equal to `reorder_level`. | `P-2031` has 2 on hand and a reorder level of 5. |
| Stock shortfall | A visit used more than were on hand, so `quantity_on_hand` goes below zero. | `P-1180` had 1 on hand and a visit used 3, leaving -2. |

### Database

| Table | Columns | Keys |
| --- | --- | --- |
| `equipment` | `serial_number`, `equipment_type` | Primary key `serial_number` |
| `visits` | `visit_id`, `serial_number`, `technician`, `visit_date`, `problem_code`, `outcome` | Primary key `visit_id`. Foreign key `serial_number` to `equipment` |
| `parts_used` | `id`, `visit_id`, `part_number`, `quantity` | Primary key `id`. Foreign key `visit_id` to `visits` |
| `stock` | `part_number`, `description`, `quantity_on_hand`, `reorder_level` | Primary key `part_number` |

`parts_used.part_number` has no foreign key to `stock`. An unknown part can be stored, and the 1.1.0 rule can flag it, without a schema change. Both versions then read the same tables, so a rollback from 1.1.0 to 1.0.0 keeps the history.

`quantity_on_hand` may be negative. A negative count is how a shortfall stays visible.

A visit, the parts used on that visit, and the stock change are saved in one transaction. If the save fails, none of those writes remain.

### Environment variable and Release 1.1.0

The database path comes from `SERVICE_DB_PATH`. Inside the container the default is `/data/service.db`.

Release 1.1.0 adds one rule, **unknown part**: flag any `parts_used` row whose part number is not in `stock`. It needs no schema change, only a new `FlagRule` subclass and a `LEFT JOIN` query.

### Presentation

Speaking order: Natalie King, Julian Marchington, Shreyaa Lakshmivaragan, Harshitha Reddy Gundavarapu.

Screen sharer and demo driver: Harshitha Reddy Gundavarapu. The same person holds the screen for the page and the live demo.

## Interface contracts

These signatures are what each person builds against. Paths are `str` or `pathlib.Path`. `Settings` holds `repeat_failure_count`, `repeat_failure_window_days`, and `part_number_pattern`.

```python
# models.py and loader.py (Natalie)
@dataclass(frozen=True)
class ServiceVisit:  # one row, one part
    visit_id: str
    serial_number: str
    equipment_type: str
    technician: str
    visit_date: date
    problem_code: str
    part_number: str
    quantity_used: int
    outcome: str

@dataclass(frozen=True)
class StockRecord:
    part_number: str
    description: str
    quantity_on_hand: int
    reorder_level: int

@dataclass(frozen=True)
class Rejection:
    source: str
    line_number: int
    raw: dict
    reason: str

def load_visits(path) -> tuple[list[ServiceVisit], list[Rejection]]: ...
def load_stock(path) -> tuple[list[StockRecord], list[Rejection]]: ...
def load_settings(path) -> Settings: ...  # raises SettingsError

# db.py (Julian)
def connect(path=None) -> sqlite3.Connection: ...  # foreign_keys ON
def init_db(conn) -> None: ...
def load_stock_records(conn, records) -> None: ...
@dataclass
class SaveResult:
    saved: int                     # visits saved by this call
    duplicates: list[str]          # visit_ids already in the database, skipped
    failed: list[tuple[str, str]]  # (visit_id, reason); the rest still save

def save_visit(conn, rows: list[ServiceVisit]) -> None: ...  # one visit, one transaction; ValueError if rows disagree
def save_visits(conn, rows: list[ServiceVisit]) -> SaveResult: ...  # groups by visit_id, one transaction per visit

# Queries: each returns list[dict], always in the same order.
def history_for_serial(conn, serial_number) -> list[dict]: ...
# keys: visit_id, visit_date, technician, problem_code, outcome, part_number, quantity
# one row per part; a visit with no parts has part_number and quantity None
# ordered by visit_date, visit_id, then part
def all_visits(conn) -> list[dict]: ...
# keys: visit_id, serial_number, visit_date, outcome
# ordered by serial_number, visit_date, visit_id
def low_stock_parts(conn) -> list[dict]: ...
# keys: part_number, description, quantity_on_hand, reorder_level
# quantity_on_hand <= reorder_level (negative included), ordered by part_number
def unknown_parts(conn) -> list[dict]: ...
# keys: visit_id, serial_number, visit_date, part_number, quantity
# parts used that are not in stock (1.1.0 rule), ordered by visit_date, visit_id, then part

# rules/base.py (Shreyaa)
@dataclass(frozen=True)
class Flag:
    rule: str
    serial_number: str | None
    part_number: str | None
    visit_dates: list[date]
    quantity: int | None
    message: str

class FlagRule(ABC):
    name: str
    def evaluate(self, conn, settings) -> list[Flag]: ...
```

The command line entry point is `service-tracker`, mapped to `service_tracker.cli:main`. `run` loads the files, saves history, and prints the report. `history SW-4410` prints the saved visits for that serial number.

## Run

Install and test on your machine:

```bash
python -m pip install -e ".[dev]"
pytest -q
```

The integration test runs `run` on `data/visits.csv`, `data/stock.csv`, and `data/settings.json`. It checks the printed report and the saved row counts: 40 visits, 46 parts used, and 12 stock rows, including repeat failure `SW-4410`, low stock `P-2031` and `P-3307`, shortfall `P-1180`, and 4 rejected rows. It does not start Docker, does not check the volume, does not upgrade or roll back, and does not try large files.

Build and run Release 1.0.0. The sample files inside the image are in `sample_data`. The database is on the volume, at `/data/service.db`. This output is from a clean volume.

```bash
docker build -t service-tracker:1.0.0 .
docker volume create readme-100
docker run --rm -v readme-100:/data service-tracker:1.0.0
```

```text
naming to docker.io/library/service-tracker:1.0.0 done
```

```text
4 rows rejected:
line 9: serial_number is missing
line 21: quantity_used is negative (-2)
line 31: visit_date is not an ISO date (2026-13-05)
line 40: quantity_used is not a whole number (two)

Service Visit Report

Visits loaded:    40
Visits saved:     40
Duplicates:       0
Rejected:         4
Serials checked:  15

Repeat failures
  Serial number:  SW-4410
  Visit dates:    2026-10-02, 2026-10-11, 2026-10-24
  Message:        SW-4410: 3 visits in 22 days (limit 3 in 30)

Low stock
  Part number:    P-1180
  Quantity:       -2
  Message:        P-1180 has -2 on hand, at or below its reorder level of 2

  Part number:    P-2031
  Quantity:       2
  Message:        P-2031 has 2 on hand, at or below its reorder level of 5

  Part number:    P-3307
  Quantity:       4
  Message:        P-3307 has 4 on hand, at or below its reorder level of 4

Stock shortfalls
  Part number:    P-1180
  Quantity:       -2
  Message:        P-1180: -2 on hand

The tool only flags and reports issues.
It does not order parts, schedule repairs,
or decide whether equipment should be replaced.
```

History for the repeat-failure serial, using the same volume:

```bash
docker run --rm -v readme-100:/data service-tracker:1.0.0 history SW-4410
```

```text
History for SW-4410
V-0139  2026-10-02  A. Okafor  PWR  failed  P-1001 x1
V-0141  2026-10-11  B. Lindqvist  PWR  replaced_part  P-1001 x1
V-0144  2026-10-24  C. Moreau  PWR  escalated  P-1002 x1
```
