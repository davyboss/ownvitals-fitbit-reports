from datetime import date, datetime

from pydantic import BaseModel, Field


class JournalEventInput(BaseModel):
    category: str
    subtype: str | None = None
    occurred_at: datetime
    quantity: float | None = Field(default=None, ge=0)
    unit: str | None = None
    dose: float | None = Field(default=None, ge=0)
    dose_unit: str | None = None
    duration_min: int | None = Field(default=None, ge=0)
    intensity: float | None = Field(default=None, ge=0, le=10)
    note: str | None = None
    original_text: str


class ProductivityCheckinInput(BaseModel):
    local_date: date
    period: str
    energy: int | None = Field(default=None, ge=1, le=10)
    sleep_quality: int | None = Field(default=None, ge=1, le=10)
    persistence: int | None = Field(default=None, ge=1, le=10)
    work_quality: int | None = Field(default=None, ge=1, le=10)
    focus: int | None = Field(default=None, ge=1, le=10)
    mood: int | None = Field(default=None, ge=1, le=10)
    stress: int | None = Field(default=None, ge=1, le=10)
    deep_work_min: int | None = Field(default=None, ge=0)
    priority: str | None = None
    note: str | None = None
    original_text: str
