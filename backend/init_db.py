"""
Creates the FitCheck.AI tables (safe to run again: every table is
CREATE TABLE IF NOT EXISTS).

    python init_db.py
"""

import sys

from config import Config
from db import apply_schema, connect


def main():
    if not Config.DB_PASSWORD:
        sys.exit("Set DB_HOST, DB_USER, DB_PASSWORD and DB_NAME first.")
    c = connect()
    try:
        apply_schema(c)
    finally:
        c.close()
    print(f"FitCheck.AI tables ready in {Config.DB_NAME} on {Config.DB_HOST}.")


if __name__ == "__main__":
    main()
