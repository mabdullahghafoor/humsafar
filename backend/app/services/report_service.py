"""
Automatic summary reports (Task 7.2, FR-Q2).

What      A PDF with the adherence and vitals trends of one Dependent for one period (the numbers of Task 7.1), made for one
          Guardian and kept in the app (stored encrypted like the Medical Vault files). The Guardian is told with a standard
          notification when a scheduled one is ready.
Schedule  A Guardian switches a weekly or monthly report ON for a Dependent (`PUT .../reports/schedule`); OFF = delete it. It is
          per Guardian: every Guardian chooses for themselves. The background job (every minute) makes the report of the LAST
          FINISHED period once: weekly = the last Monday-to-Sunday week, monthly = the last calendar month (local days,
          MEDICATION_TIMEZONE). A period that ended before the schedule was switched on is not made (clarification 169).
Manual    `POST .../reports` makes one now for the last 7 to 90 days, today included (also used for the demo).
Who       Guardians only. Adherence needs `medication_management`, vitals need `health_records` (Primary always). The report only
          contains the sections the Guardian is allowed to see when it is made, and downloading needs the permission of every
          section it contains (a Guardian who loses a permission can no longer open an older report that shows that data).
Keep      At most REPORTS_MAX_PER_PAIR per Guardian and Dependent (manual ones are refused beyond that); the job removes reports
          older than REPORT_KEEP_DAYS. Deleted with the account (retention_service).
"""

import logging
import uuid
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import AuditLog, GuardianDependentLink, ReportSchedule, SummaryReport, User
from app.schemas.reports import ReportList, ReportOut, ScheduleOut
from app.services import analytics_service, crypto_service, linkage_service, medication_service, notification_service, permission_service
from app.services import records_service, report_pdf, storage_service

log = logging.getLogger(__name__)

KIND = {"weekly": "Weekly", "monthly": "Monthly", "custom": "Custom"}


# ------------------------------------------------------------------ access

def _guardian_only(user: User) -> None:
    if user.role != "guardian":
        raise AppError(403, "FORBIDDEN", "You do not have permission to do this.")


def _sections(db: Session, user: User, dependent_id: uuid.UUID) -> tuple[bool, bool, AppError | None]:
    """(may see adherence, may see vitals, the first refusal)."""
    ok, err = [], None
    for module in (medication_service.MODULE, "health_records"):
        try:
            permission_service.check_module_access(db, user, dependent_id, module)
            ok.append(True)
        except AppError as exc:
            if exc.status_code != 403:
                raise
            ok.append(False)
            err = err or exc
    return ok[0], ok[1], err


def _access(db: Session, user: User, dependent_id: uuid.UUID) -> tuple[bool, bool]:
    _guardian_only(user)
    adh, vit, err = _sections(db, user, dependent_id)
    if not adh and not vit:
        raise err
    return adh, vit


# ------------------------------------------------------------------ periods

def last_week(today: date) -> tuple[date, date]:
    """The last finished Monday-to-Sunday week."""
    end = today - timedelta(days=today.weekday() + 1)
    return end - timedelta(days=6), end


def last_month(today: date) -> tuple[date, date]:
    end = today.replace(day=1) - timedelta(days=1)
    return end.replace(day=1), end


def _file_name(r: SummaryReport) -> str:
    return f"humsafar-summary-{r.period_start:%Y-%m-%d}-to-{r.period_end:%Y-%m-%d}.pdf"


def _out(r: SummaryReport) -> ReportOut:
    return ReportOut(
        report_id=r.report_id, dependent_id=r.dependent_id, period=r.period, source=r.source, period_start=r.period_start,
        period_end=r.period_end, includes_adherence=r.includes_adherence, includes_vitals=r.includes_vitals,
        size_bytes=r.size_bytes, created_at=r.created_at, file_name=_file_name(r),
    )


# ------------------------------------------------------------------ making a report

def _make(db: Session, guardian_id: uuid.UUID, dependent_id: uuid.UUID, first: date, last: date, period: str, source: str, adh: bool, vit: bool) -> SummaryReport:
    """Build, store and save one report (commits). The file is removed again if the row cannot be saved."""
    days = (last - first).days + 1
    a = analytics_service._adherence(db, dependent_id, days, last) if adh else None
    v = analytics_service._vitals(db, dependent_id, days, None, last) if vit else None
    name = records_service._name_map(db, {dependent_id}).get(dependent_id) or "Dependent"
    pdf = report_pdf.build(person_name=name, first=first, last=last, kind=KIND[period], adherence=a, vitals=v)
    store = storage_service.get_storage("reports")
    key = store.save(crypto_service.encrypt(pdf), ".bin")
    row = SummaryReport(
        guardian_id=guardian_id, dependent_id=dependent_id, period=period, source=source, period_start=first, period_end=last,
        includes_adherence=adh, includes_vitals=vit, file_url=key, size_bytes=len(pdf),
    )
    try:
        db.add(row)
        db.commit()
    except Exception:
        db.rollback()
        store.delete(key)
        raise
    return row


def create(db: Session, user: User, dependent_id: uuid.UUID, days: int) -> ReportOut:
    adh, vit = _access(db, user, dependent_id)
    linkage_service._lock_dependent(db, dependent_id)  # one at a time per Dependent: the cap cannot be beaten
    count = db.scalar(select(func.count()).select_from(SummaryReport).where(SummaryReport.guardian_id == user.user_id, SummaryReport.dependent_id == dependent_id))
    cap = get_settings().REPORTS_MAX_PER_PAIR
    if count >= cap:
        db.rollback()
        raise AppError(409, "REPORT_LIMIT", f"{cap} reports are already saved. Delete old ones first.")
    today = datetime.now(timezone.utc).astimezone(medication_service.tz()).date()
    row = _make(db, user.user_id, dependent_id, today - timedelta(days=days - 1), today, "custom", "manual", adh, vit)
    db.add(AuditLog(actor_id=user.user_id, action="summary_report_created", target_type="summary_report", target_id=row.report_id, dependent_id=dependent_id))
    db.commit()
    return _out(row)


# ------------------------------------------------------------------ reading

def list_reports(db: Session, user: User, dependent_id: uuid.UUID, limit: int, offset: int) -> ReportList:
    _access(db, user, dependent_id)
    where = (SummaryReport.guardian_id == user.user_id, SummaryReport.dependent_id == dependent_id)
    total = db.scalar(select(func.count()).select_from(SummaryReport).where(*where))
    rows = db.scalars(select(SummaryReport).where(*where).order_by(SummaryReport.created_at.desc(), SummaryReport.report_id).limit(limit).offset(offset)).all()
    return ReportList(items=[_out(r) for r in rows], total=total, limit=limit, offset=offset)


def _mine(db: Session, user: User, dependent_id: uuid.UUID, report_id: uuid.UUID) -> SummaryReport:
    r = db.scalar(select(SummaryReport).where(SummaryReport.report_id == report_id, SummaryReport.guardian_id == user.user_id, SummaryReport.dependent_id == dependent_id))
    if r is None:
        raise AppError(404, "REPORT_NOT_FOUND", "No such report.")
    return r


def download(db: Session, user: User, dependent_id: uuid.UUID, report_id: uuid.UUID) -> tuple[bytes, str]:
    _guardian_only(user)
    r = _mine(db, user, dependent_id, report_id)
    if r.includes_adherence:
        permission_service.check_module_access(db, user, dependent_id, medication_service.MODULE)
    if r.includes_vitals:
        permission_service.check_module_access(db, user, dependent_id, "health_records")
    path = storage_service.get_storage("reports").path(r.file_url)
    if path is None:
        raise AppError(404, "FILE_NOT_FOUND", "The file of this report is no longer available.")
    try:
        pdf = crypto_service.decrypt(path.read_bytes())
    except crypto_service.DecryptError:
        raise AppError(500, "FILE_UNREADABLE", "The stored file is damaged and cannot be opened.")
    db.add(AuditLog(actor_id=user.user_id, action="summary_report_downloaded", target_type="summary_report", target_id=r.report_id, dependent_id=dependent_id))
    db.commit()
    return pdf, _file_name(r)


def delete_report(db: Session, user: User, dependent_id: uuid.UUID, report_id: uuid.UUID) -> None:
    _guardian_only(user)
    r = _mine(db, user, dependent_id, report_id)
    key = r.file_url
    db.delete(r)
    db.commit()
    storage_service.get_storage("reports").delete(key)


# ------------------------------------------------------------------ schedule

def get_schedule(db: Session, user: User, dependent_id: uuid.UUID) -> ScheduleOut:
    _access(db, user, dependent_id)
    s = db.scalar(select(ReportSchedule).where(ReportSchedule.guardian_id == user.user_id, ReportSchedule.dependent_id == dependent_id))
    return ScheduleOut(dependent_id=dependent_id, frequency=s.frequency if s else None, since=s.created_at if s else None)


def set_schedule(db: Session, user: User, dependent_id: uuid.UUID, frequency: str) -> ScheduleOut:
    _access(db, user, dependent_id)
    s = db.scalar(select(ReportSchedule).where(ReportSchedule.guardian_id == user.user_id, ReportSchedule.dependent_id == dependent_id).with_for_update())
    if s is None:
        s = ReportSchedule(guardian_id=user.user_id, dependent_id=dependent_id, frequency=frequency)
        db.add(s)
    elif s.frequency != frequency:
        s.frequency = frequency
        s.created_at = datetime.now(timezone.utc)  # a new schedule: only periods that end from now on
    try:
        db.commit()
    except IntegrityError:  # two parallel first calls
        db.rollback()
        s = db.scalar(select(ReportSchedule).where(ReportSchedule.guardian_id == user.user_id, ReportSchedule.dependent_id == dependent_id))
    db.refresh(s)
    return ScheduleOut(dependent_id=dependent_id, frequency=s.frequency, since=s.created_at)


def clear_schedule(db: Session, user: User, dependent_id: uuid.UUID) -> None:
    _guardian_only(user)  # no permission needed to switch it off
    db.execute(delete(ReportSchedule).where(ReportSchedule.guardian_id == user.user_id, ReportSchedule.dependent_id == dependent_id))
    db.commit()


# ------------------------------------------------------------------ the background job

def prune(db: Session, now: datetime) -> int:
    old = db.scalars(select(SummaryReport).where(SummaryReport.created_at < now - timedelta(days=get_settings().REPORT_KEEP_DAYS))).all()
    keys = [r.file_url for r in old]
    for r in old:
        db.delete(r)
    db.commit()
    store = storage_service.get_storage("reports")
    for k in keys:
        store.delete(k)
    return len(keys)


def sweep(db: Session, now: datetime | None = None) -> int:
    """Background job: make the report of the last finished period for every schedule that does not have it yet. Returns how many were made."""
    now = now or datetime.now(timezone.utc)
    made = 0
    schedules = db.scalars(select(ReportSchedule)).all()
    if schedules:
        today = now.astimezone(medication_service.tz()).date()
        periods = {"weekly": last_week(today), "monthly": last_month(today)}
        have = set(db.execute(
            select(SummaryReport.guardian_id, SummaryReport.dependent_id, SummaryReport.period, SummaryReport.period_start)
            .where(SummaryReport.source == "scheduled", SummaryReport.period_start.in_([p[0] for p in periods.values()]))
        ).all())
        for s in schedules:
            first, last = periods[s.frequency]
            if (s.guardian_id, s.dependent_id, s.frequency, first) in have:
                continue
            if medication_service.occurrence(last + timedelta(days=1), time(0, 0)) <= s.created_at:
                continue  # the period ended before the schedule was switched on
            try:
                made += _scheduled_one(db, s, first, last)
            except Exception:  # one bad schedule must not stop the others
                db.rollback()
                log.exception("summary report: could not make the report for schedule %s", s.schedule_id)
    prune(db, now)
    return made


def _scheduled_one(db: Session, s: ReportSchedule, first: date, last: date) -> int:
    guardian = db.get(User, s.guardian_id)
    if guardian is None or guardian.closed_at is not None or guardian.purged_at is not None or guardian.role != "guardian":
        return 0
    adh, vit, _err = _sections(db, guardian, s.dependent_id)  # also false when the link is not active any more
    if not adh and not vit:
        return 0
    try:
        row = _make(db, s.guardian_id, s.dependent_id, first, last, s.frequency, "scheduled", adh, vit)
    except IntegrityError:  # another server process made it first
        return 0
    name = records_service._name_map(db, {s.dependent_id}).get(s.dependent_id) or "your Dependent"
    notification_service.notify(
        db, s.guardian_id, "summary_report", notification_service.STANDARD,
        f"{KIND[s.frequency]} summary is ready", f"{name}: {report_pdf.period_label(first, last)}.",
        dependent_id=s.dependent_id, dedupe_key=f"summary_report:{row.report_id}", extra={"report_id": str(row.report_id)},
    )
    return 1
