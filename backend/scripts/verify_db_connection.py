"""
Task 0.3 verification script.

Run from the `backend/` folder with your venv activated:
    python scripts/verify_db_connection.py

Confirms SQLAlchemy can connect to DATABASE_URL and run a trivial query.
"""

import sys
from sqlalchemy import text

from app.core.database import engine


def main():
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version();"))
            version = result.scalar()
            print("✅ Connected successfully.")
            print(f"   PostgreSQL version: {version}")
    except Exception as e:
        print("❌ Connection failed.")
        print(f"   Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
