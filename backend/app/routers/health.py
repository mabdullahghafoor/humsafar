"""
Health-check router.

Task 0.2 deliverable: GET /health must return 200.
No auth, no DB dependency yet — this only proves the app itself is alive.
Task 0.3 will extend this (or add a separate /health/db) to also verify
the database connection once SQLAlchemy is wired up.
"""

from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check() -> dict:
    return {"status": "ok"}
