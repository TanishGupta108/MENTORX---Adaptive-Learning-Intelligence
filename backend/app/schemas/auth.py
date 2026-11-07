from __future__ import annotations

import uuid
from datetime import datetime
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

_TIMEZONES = available_timezones()


def _valid_timezone(v: str | None) -> str | None:
    if v is not None and v not in _TIMEZONES:
        raise ValueError("unknown time zone (use an IANA name such as Asia/Kolkata)")
    return v


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)
    privacy_accepted: bool
    timezone: str | None = None

    @field_validator("full_name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("name must not be blank")
        return v

    @field_validator("privacy_accepted")
    @classmethod
    def must_accept(cls, v: bool) -> bool:
        if not v:
            raise ValueError("you must accept the privacy notice to create an account")
        return v

    @field_validator("timezone")
    @classmethod
    def check_timezone(cls, v: str | None) -> str | None:
        return _valid_timezone(v)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: str
    daily_goal: int
    timezone: str
    consent_research: bool
    created_at: datetime
    enrolled_subjects: list[str] = []


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    daily_goal: int | None = Field(default=None, ge=1, le=100)
    timezone: str | None = None
    consent_research: bool | None = None

    @field_validator("timezone")
    @classmethod
    def check_timezone(cls, v: str | None) -> str | None:
        return _valid_timezone(v)


class DeleteAccountRequest(BaseModel):
    confirm_email: EmailStr
