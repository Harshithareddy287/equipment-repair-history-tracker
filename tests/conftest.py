"""Shared fixtures. Every test gets its own database in pytest's tmp_path."""
 
import pytest
 
from service_tracker.db import connect, init_db
 
 
@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "test.db")
    init_db(conn)
    yield conn
    conn.close()
 