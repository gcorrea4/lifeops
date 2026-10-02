from datetime import date as date_type
from datetime import datetime, timezone

from pydantic import BaseModel, field_validator


class SlotSuggestion(BaseModel):
    """A candidate free slot returned by GET /engine/suggest.

    Read-only — never sent by the client.
    """

    start_datetime: datetime
    end_datetime: datetime
    date: date_type


class BookRequest(BaseModel):
    """Request body for POST /engine/book.

    end_datetime is intentionally absent — the server computes it as
    start_datetime + task.duration_minutes.
    """

    task_id: int
    start_datetime: datetime

    @field_validator("start_datetime", mode="before")
    @classmethod
    def start_must_be_in_the_future(cls, v: datetime) -> datetime:
        # Normalise to an aware datetime for comparison when a tz-aware value is passed.
        if isinstance(v, datetime):
            now = datetime.now(tz=timezone.utc) if v.tzinfo is not None else datetime.now()
            if v <= now:
                raise ValueError("start_datetime must be in the future")
        return v
