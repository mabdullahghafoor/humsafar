"""
Humsafar ORM models: all 27 tables of SDS Section 9.2.

Every model module is imported here so that `Base.metadata` is fully
populated whenever `app.models` is imported. Alembic (Task 1.2) relies on
this to autogenerate the initial migration.
"""

from app.models.communication import CallLog, Message, Notification, PushToken
from app.models.directory import (
    ActivityLog,
    BookingRequest,
    HealthcareOrganization,
    HomeCareProvider,
)
from app.models.emergency import (
    EmergencyContact,
    EscalationEvent,
    WellnessCheckResponse,
    WellnessCheckSchedule,
)
from app.models.identity import (
    DependentProfile,
    GuardianDependentLink,
    GuardianProfile,
    PermissionGrant,
    User,
)
from app.models.location import Geofence, LocationLog
from app.models.medical import (
    Appointment,
    MedicalRecord,
    MedicationConfirmation,
    MedicationSchedule,
    RecordCategoryRestriction,
    RecordShare,
    VitalReading,
    WearableDevice,
)
from app.models.security import AuditLog, CameraClip, CameraDevice

__all__ = [
    "ActivityLog",
    "Appointment",
    "AuditLog",
    "BookingRequest",
    "CallLog",
    "CameraClip",
    "CameraDevice",
    "DependentProfile",
    "EmergencyContact",
    "EscalationEvent",
    "Geofence",
    "GuardianDependentLink",
    "GuardianProfile",
    "HealthcareOrganization",
    "HomeCareProvider",
    "LocationLog",
    "MedicalRecord",
    "MedicationConfirmation",
    "MedicationSchedule",
    "Message",
    "Notification",
    "PushToken",
    "PermissionGrant",
    "User",
    "RecordCategoryRestriction",
    "RecordShare",
    "VitalReading",
    "WearableDevice",
    "WellnessCheckResponse",
    "WellnessCheckSchedule",
]
