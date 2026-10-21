"""
Health-check router.

Task 0.2 deliverable: GET /health must return 200.
No auth, no DB dependency yet — this only proves the app itself is alive.
Task 0.3 will extend this (or add a separate /health/db) to also verify
the database connection once SQLAlchemy is wired up.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check() -> dict:
    return {"status": "ok"}


@router.get("/health/db")
def health_check_db(db: Session = Depends(get_db)) -> dict:
    """Confirms the app can reach PostgreSQL, not just that the app itself is up."""
    db.execute(text("SELECT 1"))
    return {"database": "connected"}
