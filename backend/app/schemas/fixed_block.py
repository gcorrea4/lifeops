from datetime import date as date_type
from datetime import datetime, time
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.models.enums import RecurrenceType


class FixedBlockBase(BaseModel):
    """Shared optional fields — used as base for Create and Update."""

    title: Optional[str] = None
    recurrence_type: Optional[RecurrenceType] = None
    weekday: Optional[int] = None
    date: Optional[date_type] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None

    @field_validator("weekday", mode="before")
    @classmethod
    def weekday_in_range(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (0 <= v <= 6):
            raise ValueError("weekday must be between 0 (Monday) and 6 (Sunday)")
        return v


class FixedBlockCreate(FixedBlockBase):
    """Request schema for creating a new FixedBlock.

    Recurrence mutual-exclusivity and spans_next_day computation are
    intentionally deferred to the router/service layer (ST-4), where the
    full record state is always available.
    """

    title: str
    recurrence_type: RecurrenceType
    start_time: time
    end_time: time
    # spans_next_day is never sent by the client — computed server-side.

    @model_validator(mode="after")
    def start_and_end_differ(self) -> "FixedBlockCreate":
        if self.start_time == self.end_time:
            raise ValueError("start_time and end_time must not be equal")
        return self


class FixedBlockUpdate(FixedBlockBase):
    """Request schema for partially updating a FixedBlock (PATCH semantics).

    All fields are Optional. No cross-field validators — the router/service
    merges this payload with the current DB record before enforcing
    recurrence mutual-exclusivity and recomputing spans_next_day.
    """

    pass


class FixedBlockRead(BaseModel):
    """Response schema — maps directly from the ORM model."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    recurrence_type: RecurrenceType
    weekday: Optional[int]
    date: Optional[date_type]
    start_time: time
    end_time: time
    spans_next_day: bool
    created_at: datetime
