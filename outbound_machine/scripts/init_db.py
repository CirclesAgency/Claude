"""
Initialise the database — creates all tables.
Safe to run multiple times (CREATE IF NOT EXISTS semantics).

Usage: python scripts/init_db.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.logging import setup_logging
from app.db.database import init_db

setup_logging()

if __name__ == "__main__":
    init_db()
    print("Database initialised successfully.")
