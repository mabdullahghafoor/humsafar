"""
Summary reports (Task 7.2, FR-Q2): a Guardian's own weekly / monthly report schedule per Dependent, and the reports made
(PDF files stored encrypted, like the Medical Vault).
"""

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, Date, Index, String, Text, UniqueConstraint, text

from app.core.database import Base
from app.models._common import fk_col, in_list, ts_col, uuid_pk

REPORT_FREQUENCIES = ("weekly", "monthly")
REPORT_PERIODS = ("weekly", "monthly", "custom")
REPORT_SOURCES = ("scheduled", "manual")


class ReportSchedule(Base):
    """One row = this Guardian gets a report for this Dependent every week / month. No row = off."""

    __tablename__ = "report_schedules"

    schedule_id = uuid_pk()
    guardian_id = fk_col("users.user_id", index=True)
    dependent_id = fk_col("dependent_profiles.user_id", index=True)
    frequency = Column(String(10), nullable=False)
    created_at = ts_col()

    __table_args__ = (
        CheckConstraint(in_list("frequency", REPORT_FREQUENCIES), name="frequency_valid"),
        UniqueConstraint("guardian_id", "dependent_id", name="uq_report_schedule_guardian_dependent"),
    )


class SummaryReport(Base):
    """One finished report for one Guardian. `file_url` is the storage key of the encrypted PDF."""

    __tablename__ = "summary_reports"

    report_id = uuid_pk()
    guardian_id = fk_col("users.user_id", index=True)
    dependent_id = fk_col("dependent_profiles.user_id", index=True)
    period = Column(String(10), nullable=False)
    source = Column(String(10), nullable=False)
    period_start = Column(Date, nullable=False)  # local days, both inclusive
    period_end = Column(Date, nullable=False)
    includes_adherence = Column(Boolean, nullable=False)
    includes_vitals = Column(Boolean, nullable=False)
    file_url = Column(Text, nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    created_at = ts_col()

    __table_args__ = (
        CheckConstraint(in_list("period", REPORT_PERIODS), name="period_valid"),
        CheckConstraint(in_list("source", REPORT_SOURCES), name="source_valid"),
        CheckConstraint("period_end >= period_start", name="period_order"),
        CheckConstraint("includes_adherence OR includes_vitals", name="has_a_section"),
        CheckConstraint("size_bytes > 0", name="size_positive"),
        # The job makes each scheduled period once per Guardian and Dependent, even if two server processes run it.
        Index("uq_summary_reports_scheduled_period", "guardian_id", "dependent_id", "period", "period_start", unique=True, postgresql_where=text("source = 'scheduled'")),
        Index("ix_summary_reports_pair_created", "guardian_id", "dependent_id", "created_at"),
    )
