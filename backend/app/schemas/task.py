from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.enums import Priority, TaskStatus


class TaskBase(BaseModel):
    """Shared optional fields — used as base for Create and Update."""

    title: Optional[str] = None
    duration_minutes: Optional[int] = None
    deadline: Optional[date] = None
    priority: Optional[Priority] = None

    @field_validator("duration_minutes", mode="before")
    @classmethod
    def duration_must_be_positive(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v <= 0:
            raise ValueError("duration_minutes must be greater than 0")
        return v


class TaskCreate(TaskBase):
    """Request schema for creating a new Task.

    status is intentionally absent — it defaults to pending at the DB level
    and is managed exclusively through engine actions (book / unbook / done).
    """

    title: str
    duration_minutes: int
    priority: Priority = Priority.medium
    # deadline is optional; deadline validation only applies on Create.

    @field_validator("deadline", mode="before")
    @classmethod
    def deadline_not_in_the_past(cls, v: Optional[date]) -> Optional[date]:
        if v is not None and v < date.today():
            raise ValueError("deadline must be today or in the future")
        return v


class TaskUpdate(TaskBase):
    """Request schema for partially updating a Task (PATCH semantics).

    All fields are Optional. status is excluded — managed only through
    engine actions.
    """

    pass


class TaskRead(BaseModel):
    """Response schema — maps directly from the ORM model."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    duration_minutes: int
    deadline: Optional[date]
    priority: Priority
    status: TaskStatus
    created_at: datetime
