from dataclasses import dataclass
from datetime import date

OUTCOMES = {"fixed", "failed", "replaced_part", "escalated"}

@dataclass(frozen=True)
class ServiceVisit:  # one CSV row = one part used; rows of one visit share visit_id
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
    source: str        # "visits" or "stock"
    line_number: int   # CSV line, header = line 1
    raw: dict
    reason: str
