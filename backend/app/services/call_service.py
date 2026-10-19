"""
Voice and video calls (Task 4.4, FR-E2): who is calling whom, ringing, accept / decline / end, history.
The audio and video themselves go through the call provider's SDK (decision 4.1); this file only manages the call's life
and hands out join tokens (call_provider.py).

Life of a call:  ringing -> accepted -> ended          (answered, then someone hangs up, or the server cuts it at CALL_MAX_S)
                 ringing -> declined                   (the callee says no)
                 ringing -> cancelled                  (the caller hangs up before an answer)
                 ringing -> missed                     (nobody answered within CALL_RING_S)
Rules
- Guardian <-> linked Dependent only. Primary always; a Secondary needs `communication` (same check as messages).
- "Calls shall require the receiving party to actively accept" (FR-E2): only the callee can accept, and the join token goes to
  the callee only AFTER accepting.
- One open call per person at a time. Calling the same person again while it rings returns the same call (`already_active`).
- Every action is safe to repeat (a second "end" or "decline" just returns the call).
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, text, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import CallLog, User
from app.schemas.call import CallIn, CallList, CallOut, JoinInfo
from app.services import call_provider
from app.services import messaging_service as ms
from app.services import notification_service as ns

OPEN = ("ringing", "accepted")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _lock_users(db: Session, *ids: uuid.UUID) -> None:
    """Two people calling each other at the same moment must not both succeed: lock both, always in the same order."""
    for k in sorted(str(i) for i in ids):
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"call:{k}"})


def _dependent_of(db: Session, c: CallLog) -> uuid.UUID:
    caller = db.get(User, c.caller_id)
    return c.caller_id if caller.role == "dependent" else c.callee_id


def _name(db: Session, user_id: uuid.UUID, fallback: str) -> str:
    u = db.get(User, user_id)
    return ((u.full_name or "").strip() if u else "") or fallback


def _open_calls(db: Session, *ids: uuid.UUID) -> list[CallLog]:
    return list(
        db.scalars(
            select(CallLog)
            .where(CallLog.status.in_(OPEN), or_(CallLog.caller_id.in_(ids), CallLog.callee_id.in_(ids)))
            .order_by(CallLog.started_at)
            .with_for_update()
        )
    )


def _close_if_late(db: Session, c: CallLog, now: datetime) -> bool:
    """Ringing too long -> missed. Open too long -> ended. Returns True if it changed (the caller commits)."""
    s = get_settings()
    if c.status == "ringing" and now >= c.started_at + timedelta(seconds=s.CALL_RING_S):
        c.status, c.ended_at = "missed", c.started_at + timedelta(seconds=s.CALL_RING_S)
        return True
    if c.status == "accepted" and now >= c.answered_at + timedelta(seconds=s.CALL_MAX_S):
        c.status, c.ended_at, c.duration_s = "ended", c.answered_at + timedelta(seconds=s.CALL_MAX_S), s.CALL_MAX_S
        return True
    return False


def _tell_missed(db: Session, c: CallLog) -> None:
    caller = _name(db, c.caller_id, "Someone")
    ns.notify(
        db, c.callee_id, "missed_call", ns.STANDARD, f"Missed call from {caller}", "Voice call" if c.type == "voice" else "Video call",
        dependent_id=_dependent_of(db, c), dedupe_key=f"missed_call:{c.call_id}",
        extra={"call_id": str(c.call_id), "call_type": c.type, "caller_id": str(c.caller_id)},
    )


def _view(db: Session, c: CallLog, me: User, *, already: bool = False) -> CallOut:
    s = get_settings()
    other_id = c.callee_id if c.caller_id == me.user_id else c.caller_id
    join = None
    may_join = c.status == "accepted" or (c.status == "ringing" and c.caller_id == me.user_id)
    if may_join:
        info = call_provider.join_info(c.room_id, str(me.user_id), c.type)
        join = JoinInfo(**info) if info else None
    return CallOut(
        call_id=c.call_id, caller_id=c.caller_id, callee_id=c.callee_id, type=c.type, status=c.status, started_at=c.started_at,
        answered_at=c.answered_at, ended_at=c.ended_at, duration_s=c.duration_s, from_me=c.caller_id == me.user_id,
        other_name=_name(db, other_id, ""), already_active=already,
        ring_expires_at=c.started_at + timedelta(seconds=s.CALL_RING_S) if c.status == "ringing" else None, join=join,
    )


def _party(db: Session, me: User, call_id: uuid.UUID, *, lock: bool) -> CallLog:
    q = select(CallLog).where(CallLog.call_id == call_id)
    c = db.scalar(q.with_for_update() if lock else q)
    if c is None or me.user_id not in (c.caller_id, c.callee_id):
        raise AppError(404, "CALL_NOT_FOUND", "Call not found.")
    return c


# ------------------------------------------------------------ actions

def start(db: Session, me: User, data: CallIn) -> CallOut:
    other, dep_id = ms._pair(db, me, data.callee_id)
    _lock_users(db, me.user_id, other.user_id)
    now = _now()
    late = [c for c in _open_calls(db, me.user_id, other.user_id) if _close_if_late(db, c, now)]
    if late:
        db.flush()
    active = _open_calls(db, me.user_id, other.user_id)
    for c in active:
        if c.caller_id == me.user_id and c.callee_id == other.user_id:
            out = _view(db, c, me, already=True)
            db.commit()
            for l in late:
                _tell_missed(db, l)
            return out
    if active:
        db.commit()
        for l in late:
            _tell_missed(db, l)
        raise AppError(409, "USER_BUSY", "You or the other person is already in a call.")
    call_id = uuid.uuid4()
    c = CallLog(call_id=call_id, caller_id=me.user_id, callee_id=other.user_id, type=data.type, status="ringing", room_id=f"call_{call_id.hex}")
    db.add(c)
    db.commit()
    db.refresh(c)
    for l in late:
        _tell_missed(db, l)
    ns.notify(
        db, other.user_id, "incoming_call", ns.CRITICAL, f"{_name(db, me.user_id, 'Someone')} is calling",
        "Video call" if c.type == "video" else "Voice call", dependent_id=dep_id, dedupe_key=f"call:{c.call_id}",
        extra={"call_id": str(c.call_id), "call_type": c.type, "caller_id": str(me.user_id),
               "expires_at": (c.started_at + timedelta(seconds=get_settings().CALL_RING_S)).isoformat()},
    )
    return _view(db, c, me)


def _settle(db: Session, c: CallLog) -> None:
    """Apply the time rules to a call we already hold locked; tell the callee if it just became missed."""
    was = c.status
    if _close_if_late(db, c, _now()):
        db.commit()
        if was == "ringing":
            _tell_missed(db, c)
        db.refresh(c)


def accept(db: Session, me: User, call_id: uuid.UUID) -> CallOut:
    c = _party(db, me, call_id, lock=True)
    _settle(db, c)
    if c.callee_id != me.user_id:
        db.rollback()
        raise AppError(403, "FORBIDDEN", "Only the person being called can accept.")
    if c.status == "accepted":  # repeat: same answer
        out = _view(db, c, me)
        db.rollback()
        return out
    if c.status != "ringing":
        db.rollback()
        raise AppError(409, "CALL_NOT_RINGING", f"This call is {c.status}.", {"status": c.status})
    try:
        ms._pair(db, me, c.caller_id)  # the permission may have been taken away while it rang
    except AppError:
        db.rollback()
        raise
    c.status, c.answered_at = "accepted", _now()
    db.commit()
    db.refresh(c)
    return _view(db, c, me)


def decline(db: Session, me: User, call_id: uuid.UUID) -> CallOut:
    c = _party(db, me, call_id, lock=True)
    _settle(db, c)
    if c.callee_id != me.user_id:
        db.rollback()
        raise AppError(403, "FORBIDDEN", "Only the person being called can decline.")
    if c.status == "declined":
        out = _view(db, c, me)
        db.rollback()
        return out
    if c.status != "ringing":
        db.rollback()
        raise AppError(409, "CALL_NOT_RINGING", f"This call is {c.status}.", {"status": c.status})
    c.status, c.ended_at = "declined", _now()
    db.commit()
    db.refresh(c)
    return _view(db, c, me)


def end(db: Session, me: User, call_id: uuid.UUID) -> CallOut:
    c = _party(db, me, call_id, lock=True)
    _settle(db, c)
    now = _now()
    if c.status == "ringing":
        if c.caller_id == me.user_id:
            c.status, c.ended_at = "cancelled", now
            db.commit()
            _tell_missed(db, c)
        else:
            c.status, c.ended_at = "declined", now
            db.commit()
        db.refresh(c)
    elif c.status == "accepted":
        c.status, c.ended_at = "ended", now
        c.duration_s = max(0, int((now - c.answered_at).total_seconds()))
        db.commit()
        db.refresh(c)
    else:
        db.rollback()  # already finished: just show it
    return _view(db, c, me)


def get(db: Session, me: User, call_id: uuid.UUID) -> CallOut:
    c = _party(db, me, call_id, lock=True)
    _settle(db, c)
    out = _view(db, c, me)
    db.rollback()
    return out


def history(db: Session, me: User, *, limit: int, before: datetime | None) -> CallList:
    q = select(CallLog).where(or_(CallLog.caller_id == me.user_id, CallLog.callee_id == me.user_id))
    if before is not None:
        q = q.where(CallLog.started_at < before)
    rows = list(db.scalars(q.order_by(CallLog.started_at.desc(), CallLog.call_id.desc()).limit(limit + 1)))
    more = len(rows) > limit
    rows = rows[:limit]
    items = []
    for c in rows:  # a call that nobody closed shows its true state
        _settle_readonly(c)
        items.append(_view(db, c, me))
    return CallList(items=items, next_before=rows[-1].started_at if more else None)


def _settle_readonly(c: CallLog) -> None:
    """For the list only (not saved): show 'missed' / 'ended' if the time rules already apply. The sweep saves it for real."""
    s = get_settings()
    now = _now()
    if c.status == "ringing" and now >= c.started_at + timedelta(seconds=s.CALL_RING_S):
        c.status = "missed"
    elif c.status == "accepted" and now >= c.answered_at + timedelta(seconds=s.CALL_MAX_S):
        c.status = "ended"
    # (not committed: the session is only read in `history`)


# ------------------------------------------------------------ background job

def sweep(db: Session, now: datetime | None = None) -> int:
    """Every minute: ringing calls past CALL_RING_S become 'missed' (the callee is told), open calls past CALL_MAX_S are ended."""
    s = get_settings()
    now = now or _now()
    rows = db.scalars(
        select(CallLog)
        .where(
            or_(
                (CallLog.status == "ringing") & (CallLog.started_at <= now - timedelta(seconds=s.CALL_RING_S)),
                (CallLog.status == "accepted") & (CallLog.answered_at <= now - timedelta(seconds=s.CALL_MAX_S)),
            )
        )
        .with_for_update(skip_locked=True)
    ).all()
    missed = []
    for c in rows:
        was = c.status
        if _close_if_late(db, c, now) and was == "ringing":
            missed.append(c)
    db.commit()
    for c in missed:
        _tell_missed(db, c)
    return len(rows)
