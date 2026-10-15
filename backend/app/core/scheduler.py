"""
Tiny background-job runner (Task 2.3).

Some things happen because NOTHING arrives: a phone that has gone silent sends no request
to react to. A job that wakes up every SCHEDULER_TICK_S seconds finds those cases. Phase 3 adds
its timers here too (missed doses, wellness-check grace periods, escalation timeouts).

How it works: one asyncio task, started with the app, calls each registered job in a worker thread
with its own database session. A failing job is logged and tried again next tick; it can never
stop the loop or the API. Several app processes may run the same job at once; jobs must be
safe for that (they lock the Dependent row before changing anything).
"""

import asyncio
import logging
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal

log = logging.getLogger("humsafar.scheduler")

JOBS: list[tuple[str, Callable[[Session], object]]] = []


def register(name: str, fn: Callable[[Session], object]) -> None:
    JOBS.append((name, fn))


def run_jobs_once() -> dict[str, str]:
    """Run every job once. Returns name -> 'ok' or the error text (used by the loop and by tests)."""
    results: dict[str, str] = {}
    for name, fn in JOBS:
        db = SessionLocal()
        try:
            fn(db)
            results[name] = "ok"
        except Exception as exc:  # noqa: BLE001  (a bad job must not kill the loop)
            db.rollback()
            log.exception("job %s failed", name)
            results[name] = f"error: {exc}"
        finally:
            db.close()
    return results


async def loop() -> None:
    tick = get_settings().SCHEDULER_TICK_S
    while True:
        await asyncio.sleep(tick)
        await asyncio.to_thread(run_jobs_once)
