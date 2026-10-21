"""Account closure (Task 6.7, FR-O1)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class PasswordIn(BaseModel):
    password: str = Field(min_length=1, max_length=128, description="The password of the person doing this (confirmation).")


class ReopenIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ClosureOut(BaseModel):
    user_id: uuid.UUID
    status: str = Field(description="closed or reopened")
    closed_at: datetime | None
    delete_after: datetime | None = Field(description="From this time the data is deleted or anonymized. Null once reopened.")
