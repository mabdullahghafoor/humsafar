"""
Location & Geofence module (SDS 8 / 9.2): geofences, location_logs.

Traces to: FR-C1, FR-C2, FR-C3, FR-C4, FR-L1.
"""

from sqlalchemy import CheckConstraint, Column, Float, Index, Integer, String

from app.core.database import Base
from app.models._common import fk_col, ts_col, uuid_pk


class Geofence(Base):
    __tablename__ = "geofences"

    geofence_id = uuid_pk()
    dependent_id = fk_col("dependent_profiles.user_id", index=True)
    name = Column(String(100), nullable=False)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    radius_m = Column(Float, nullable=False)
    created_by = fk_col("users.user_id")

    __table_args__ = (
        CheckConstraint("radius_m > 0", name="radius_positive"),
        CheckConstraint("lat BETWEEN -90 AND 90", name="lat_range"),
        CheckConstraint("lng BETWEEN -180 AND 180", name="lng_range"),
    )


class LocationLog(Base):
    __tablename__ = "location_logs"

    log_id = uuid_pk()
    dependent_id = fk_col("dependent_profiles.user_id")
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    recorded_at = ts_col()
    battery_level = Column(Integer, nullable=True)  # percent; also feeds FR-L1

    __table_args__ = (
        CheckConstraint("lat BETWEEN -90 AND 90", name="lat_range"),
        CheckConstraint("lng BETWEEN -180 AND 180", name="lng_range"),
        CheckConstraint(
            "battery_level IS NULL OR battery_level BETWEEN 0 AND 100",
            name="battery_range",
        ),
        # Most frequent query: latest / historical points for one Dependent.
        Index("ix_location_logs_dependent_recorded", "dependent_id", "recorded_at"),
    )
