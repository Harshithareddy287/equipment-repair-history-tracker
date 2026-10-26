"""Write repeatable synthetic visit, stock and settings files for the demo.

    python scripts/generate_data.py --seed 42 --with-unknown-parts

The same seed always gives byte-identical files. Every serial, technician
and part here is made up. Random visits fill in the background; the cases
each demo moment needs are planted by hand so the expected flags never move.
"""

import argparse
import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path

VISIT_FIELDS = [
    "visit_id", "serial_number", "equipment_type", "technician", "visit_date",
    "problem_code", "part_number", "quantity_used", "outcome",
]
STOCK_FIELDS = ["part_number", "description", "quantity_on_hand", "reorder_level"]
SETTINGS = {
    "repeat_failure_count": 3,
    "repeat_failure_window_days": 30,
    "part_number_pattern": "^P-\\d{4}$",
}

# A tuple, not models.OUTCOMES: set order changes between runs, which would
# break the same-seed-same-files promise.
OUTCOMES = ("fixed", "failed", "replaced_part", "escalated")
TECHNICIANS = ("A. Okafor", "B. Lindqvist", "C. Moreau", "D. Tanaka")
PROBLEM_CODES = ("PWR", "FAN", "DISK", "MEM", "NIC", "PORT", "FIRMWARE", "OVERHEAT")

SERIALS = {
    "SW-4410": "switch", "SW-4411": "switch", "SW-5120": "switch",
    "RT-2201": "router", "RT-2245": "router", "RT-3310": "router",
    "SRV-1001": "server", "SRV-1017": "server", "SRV-1088": "server", "SRV-2040": "server",
    "FW-0501": "firewall", "FW-0533": "firewall",
    "ST-7001": "storage", "ST-7012": "storage", "ST-7030": "storage",
}

PARTS = {
    "P-1001": "PSU 500W",
    "P-1002": "Chassis fan",
    "P-1180": "SFP+ transceiver",
    "P-1450": "DIMM 32GB",
    "P-2031": "PSU 750W",
    "P-2210": "SSD 960GB",
    "P-2675": "HDD 4TB",
    "P-3307": "Fan tray",
    "P-3512": "NIC 25GbE",
    "P-4020": "RAID controller battery",
    "P-4188": "Console cable",
    "P-5230": "Supervisor module",
}

# Stock for the planted parts is fixed; every other part gets enough stock
# that it can never go low, so only the planted parts raise stock flags.
PLANTED_STOCK = {
    "P-2031": (4, 5),  # (quantity_on_hand, reorder_level)
    "P-3307": (6, 4),
    "P-1180": (1, 2),
}
RANDOM_PARTS = [p for p in PARTS if p not in PLANTED_STOCK]

REPEAT_SERIAL = "SW-4410"
CLEAN_VISITS = 40
RANDOM_START = date(2026, 1, 5)
RANDOM_DAYS = 268  # up to 2026-09-29, before the planted October visits
FIRST_VISIT_NUMBER = 101


def visit(day, serial, technician, problem, outcome, parts):
    return {
        "visit_date": day, "serial_number": serial,
        "equipment_type": SERIALS.get(serial, ""), "technician": technician,
        "problem_code": problem, "outcome": outcome, "parts": parts,
    }


def planted_visits():
    return [
        # Demo: repeat failure. SW-4410 has 3 visits inside 30 days.
        visit(date(2026, 10, 2), REPEAT_SERIAL, "A. Okafor", "PWR", "failed", [("P-1001", 1)]),
        visit(date(2026, 10, 11), REPEAT_SERIAL, "B. Lindqvist", "PWR", "replaced_part", [("P-1001", 1)]),
        visit(date(2026, 10, 24), REPEAT_SERIAL, "C. Moreau", "PWR", "escalated", [("P-1002", 1)]),
        # Demo: low stock. P-2031 goes from 4 to 2, below its reorder level of 5.
        visit(date(2026, 10, 8), "SRV-1017", "D. Tanaka", "PWR", "replaced_part", [("P-2031", 2)]),
        # Demo: low stock at the boundary. P-3307 goes from 6 to 4, equal to its reorder level.
        visit(date(2026, 10, 14), "SW-5120", "A. Okafor", "FAN", "replaced_part", [("P-3307", 2)]),
        # Demo: stock shortfall. P-1180 had 1 on hand and this visit uses 3, leaving -2.
        visit(date(2026, 10, 19), "RT-2245", "D. Tanaka", "PORT", "replaced_part", [("P-1180", 3)]),
    ]


def too_close(dates):
    """True if any 3 visits fall within 31 days, a margin past the 30-day rule."""
    dates = sorted(dates)
    return any(dates[i + 2] - dates[i] <= timedelta(days=31) for i in range(len(dates) - 2))


def random_visits(rng, existing, count):
    """Background visits that can never trip the repeat-failure rule."""
    dates_by_serial = {s: [] for s in SERIALS}
    for v in existing:
        dates_by_serial[v["serial_number"]].append(v["visit_date"])
    others = [s for s in SERIALS if s != REPEAT_SERIAL]
    # Every serial gets at least one visit, then the rest are spread at random.
    serials = others + [rng.choice(others) for _ in range(count - len(others))]

    visits = []
    for serial in serials:
        while True:
            day = RANDOM_START + timedelta(days=rng.randrange(RANDOM_DAYS))
            if not too_close(dates_by_serial[serial] + [day]):
                break
        dates_by_serial[serial].append(day)
        parts = rng.sample(RANDOM_PARTS, 2 if rng.random() < 0.25 else 1)
        visits.append(visit(
            day, serial, rng.choice(TECHNICIANS), rng.choice(PROBLEM_CODES),
            rng.choice(OUTCOMES), [(p, rng.randint(1, 2)) for p in parts],
        ))
    return visits


def bad_rows(rng):
    """Demo: bad records. Each one is rejected at load and never saved.

    Keyed by where it sits among the visits, so the missing serial is always
    V-0107, the example in the README.
    """
    def row(serial, day, part, quantity):
        return {
            "serial_number": serial, "equipment_type": SERIALS.get(serial, "router"),
            "technician": rng.choice(TECHNICIANS), "visit_date": day,
            "problem_code": rng.choice(PROBLEM_CODES), "part_number": part,
            "quantity_used": quantity, "outcome": rng.choice(OUTCOMES),
        }

    return {
        6: row("", "2026-02-03", "P-3512", "1"),           # missing serial
        15: row("FW-0501", "2026-04-14", "P-1450", "-2"),  # negative quantity
        24: row("ST-7012", "2026-13-05", "P-2675", "1"),   # invalid date
        33: row("RT-3310", "2026-07-21", "P-4188", "two"), # non-numeric quantity
    }


def visit_id(index):
    return f"V-{FIRST_VISIT_NUMBER + index:04d}"


def visit_rows(clean, bad):
    """Number visits in date order with the bad rows slotted in, one row per part."""
    clean = sorted(clean, key=lambda v: (v["visit_date"], v["serial_number"]))
    rows = []
    for index in range(len(clean) + len(bad)):
        if index in bad:
            rows.append({"visit_id": visit_id(index), **bad[index]})
            continue
        v = clean.pop(0)
        for part, quantity in v["parts"]:
            rows.append({
                "visit_id": visit_id(index), "serial_number": v["serial_number"],
                "equipment_type": v["equipment_type"], "technician": v["technician"],
                "visit_date": v["visit_date"].isoformat(), "problem_code": v["problem_code"],
                "part_number": part, "quantity_used": str(quantity), "outcome": v["outcome"],
            })
    return rows


def stock_rows(rng, clean):
    usage = {p: 0 for p in PARTS}
    for v in clean:
        for part, quantity in v["parts"]:
            usage[part] += quantity
    rows = []
    for part, description in PARTS.items():
        if part in PLANTED_STOCK:
            on_hand, reorder = PLANTED_STOCK[part]
        else:
            reorder = rng.randint(3, 8)
            on_hand = reorder + usage[part] + rng.randint(5, 20)
        rows.append({
            "part_number": part, "description": description,
            "quantity_on_hand": str(on_hand), "reorder_level": str(reorder),
        })
    return rows


def unknown_part_rows(first_index):
    """Demo (1.1.0): unknown part. Part numbers match the pattern but are not in stock.

    Fixed rows on new serials, using no randomness, so visits.csv is the
    same with or without --with-unknown-parts and no other flag changes.
    """
    return [
        {
            "visit_id": visit_id(first_index), "serial_number": "RT-9001",
            "equipment_type": "router", "technician": "B. Lindqvist",
            "visit_date": "2026-10-20", "problem_code": "PORT",
            "part_number": "P-9901", "quantity_used": "1", "outcome": "replaced_part",
        },
        {
            "visit_id": visit_id(first_index + 1), "serial_number": "SRV-9002",
            "equipment_type": "server", "technician": "C. Moreau",
            "visit_date": "2026-10-22", "problem_code": "MEM",
            "part_number": "P-9902", "quantity_used": "2", "outcome": "replaced_part",
        },
    ]


def write_csv(path, fields, rows):
    # Fixed "\n" endings so files are byte-identical on every OS.
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def generate(seed, out, with_unknown_parts=False):
    rng = random.Random(seed)
    clean = planted_visits()
    clean += random_visits(rng, clean, CLEAN_VISITS - len(clean))
    bad = bad_rows(rng)
    visits = visit_rows(clean, bad)
    stock = stock_rows(rng, clean)

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "visits.csv", VISIT_FIELDS, visits)
    write_csv(out / "stock.csv", STOCK_FIELDS, stock)
    (out / "settings.json").write_text(json.dumps(SETTINGS, indent=2) + "\n", encoding="utf-8")
    if with_unknown_parts:
        extra = unknown_part_rows(len(clean) + len(bad))
        write_csv(out / "visits_unknown_parts.csv", VISIT_FIELDS, visits + extra)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=42, help="random seed (default 42)")
    parser.add_argument("--out", default="data/", help="output folder (default data/)")
    parser.add_argument(
        "--with-unknown-parts", action="store_true",
        help="also write visits_unknown_parts.csv with two parts missing from stock",
    )
    args = parser.parse_args(argv)
    generate(args.seed, args.out, args.with_unknown_parts)


if __name__ == "__main__":
    main()
