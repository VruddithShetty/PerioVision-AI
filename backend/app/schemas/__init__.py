"""Request validation schemas (pydantic). Unknown fields are rejected, types are strict,
and nothing from a request body can reach MongoDB as an operator (no `$ne`, `$gt`, ...)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LoginIn(Strict):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class MfaIn(Strict):
    mfa_token: str = Field(min_length=10, max_length=4096)
    code: str = Field(pattern=r"^\d{6}$")


class TotpCodeIn(Strict):
    code: str = Field(pattern=r"^\d{6}$")


class UserCreateIn(Strict):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=10, max_length=256)
    role: Literal["admin", "dentist", "technician", "auditor"]
    clinic_name: str | None = Field(default=None, max_length=120)


class UserUpdateIn(Strict):
    role: Literal["admin", "dentist", "technician", "auditor"] | None = None
    active: bool | None = None


class PatientIn(Strict):
    name: str = Field(min_length=1, max_length=120)
    age: int | None = Field(default=None, ge=0, le=120)
    sex: Literal["female", "male", "other", "unknown"] | None = None
    contact: str | None = Field(default=None, max_length=60)
    notes: str | None = Field(default=None, max_length=2000)
    smoking_status: Literal["never", "former", "current", "unknown"] | None = "unknown"
    cigarettes_per_day: int | None = Field(default=None, ge=0, le=100)
    diabetic: bool | None = None
    hba1c: float | None = Field(default=None, ge=3.0, le=20.0)
    teeth_lost_perio: int | None = Field(default=None, ge=0, le=32)

    @field_validator("name")
    @classmethod
    def no_markup(cls, v):
        if v is not None and ("<" in v or ">" in v):
            raise ValueError("must not contain < or >")
        return v


class PatientUpdateIn(PatientIn):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    smoking_status: Literal["never", "former", "current", "unknown"] | None = None


class AnalyzeIn(Strict):
    upload_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    patient_id: int = Field(ge=1)
    visit_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class ToothCorrection(Strict):
    tooth_id: str = Field(max_length=8)
    bone_loss_pct: float | None = Field(default=None, ge=0, le=100)
    stage: Literal["I", "II", "III", "IV"] | None = None
    note: str | None = Field(default=None, max_length=500)


class ReviewIn(Strict):
    decision: Literal["approve", "correct", "reject"]
    comment: str | None = Field(default=None, max_length=2000)
    corrections: list[ToothCorrection] = Field(default_factory=list, max_length=40)


class ReportIn(Strict):
    analysis_id: str = Field(pattern=r"^AN-[a-f0-9]{12}$")


class ToothChart(Strict):
    pd: list[int] = Field(default_factory=lambda: [0] * 6, min_length=6, max_length=6)
    rec: list[int] = Field(default_factory=lambda: [0] * 6, min_length=6, max_length=6)
    bop: list[bool] = Field(default_factory=lambda: [False] * 6, min_length=6, max_length=6)
    plaque: list[bool] = Field(default_factory=lambda: [False] * 6, min_length=6, max_length=6)
    mobility: int = Field(default=0, ge=0, le=3)
    furcation: int = Field(default=0, ge=0, le=3)
    missing: bool = False

    @field_validator("pd")
    @classmethod
    def pd_range(cls, v):
        if any(x < 0 or x > 15 for x in v):
            raise ValueError("probing depths must be 0-15 mm")
        return v

    @field_validator("rec")
    @classmethod
    def rec_range(cls, v):
        if any(x < -5 or x > 15 for x in v):
            raise ValueError("recession must be -5 to 15 mm")
        return v


class PerioChartIn(Strict):
    exam_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    teeth: dict[str, ToothChart] = Field(max_length=32)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("teeth")
    @classmethod
    def fdi_keys(cls, v):
        import re
        bad = [k for k in v if not re.fullmatch(r"[1-4][1-8]", k)]
        if bad:
            raise ValueError(f"unknown FDI tooth numbers: {', '.join(bad)}")
        return v
