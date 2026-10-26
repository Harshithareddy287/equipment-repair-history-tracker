"""JM-2: load_stock_records."""
 
import sqlite3
from dataclasses import dataclass
 
import pytest
 
from service_tracker.db import load_stock_records
 
 
# Same fields as models.StockRecord, so these tests do not wait on the loader.
@dataclass(frozen=True)
class Stock:
    part_number: str
    description: str
    quantity_on_hand: int
    reorder_level: int
 
 
def stock_row(conn, part_number):
    return conn.execute(
        "SELECT * FROM stock WHERE part_number = ?", (part_number,)
    ).fetchone()
 
 
def test_new_parts_are_inserted(conn):
    load_stock_records(conn, [
        Stock("P-1001", "PSU 500W", 10, 3),
        Stock("P-1002", "Fan", 4, 2),
    ])
    assert conn.execute("SELECT COUNT(*) FROM stock").fetchone()[0] == 2
    row = stock_row(conn, "P-1001")
    assert (row["description"], row["quantity_on_hand"], row["reorder_level"]) == (
        "PSU 500W", 10, 3,
    )
 
 
def test_existing_part_updates_description_and_reorder_level(conn):
    load_stock_records(conn, [Stock("P-1001", "PSU 500W", 10, 3)])
    load_stock_records(conn, [Stock("P-1001", "PSU 550W", 10, 5)])
    row = stock_row(conn, "P-1001")
    assert (row["description"], row["reorder_level"]) == ("PSU 550W", 5)
 
 
def test_existing_part_keeps_quantity_on_hand(conn):
    load_stock_records(conn, [Stock("P-1001", "PSU 500W", 10, 3)])
    with conn:
        conn.execute("UPDATE stock SET quantity_on_hand = 7 WHERE part_number = 'P-1001'")
    load_stock_records(conn, [Stock("P-1001", "PSU 500W", 10, 3)])
    assert stock_row(conn, "P-1001")["quantity_on_hand"] == 7
 
 
def test_failed_load_saves_nothing(conn):
    with pytest.raises(sqlite3.IntegrityError):
        load_stock_records(conn, [
            Stock("P-1001", "PSU 500W", 10, 3),
            Stock("P-1002", "Fan", 4, -1),  # breaks CHECK (reorder_level >= 0)
        ])
    assert conn.execute("SELECT COUNT(*) FROM stock").fetchone()[0] == 0
 