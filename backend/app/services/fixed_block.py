"""Application-layer service functions for FixedBlock.

All business-rule validation runs on a plain candidate dict assembled from
the fully-merged state (DB record + patch payload).  The ORM object is never
mutated until every check has passed, so there is nothing to roll back on
validation failure.
"""

from fastapi import HTTPException

from app.models.enums import RecurrenceType
from app.models.fixed_block import FixedBlock
from app.schemas.fixed_block import FixedBlockUpdate


def validate_recurrence(candidate: dict) -> None:
    """Enforce recurrence mutual exclusivity on a fully-merged candidate dict.

    weekly → weekday must be int (not None), date must be None.
    once   → date must be set (not None), weekday must be None.
    """
    recurrence_type = candidate.get("recurrence_type")

    if recurrence_type == RecurrenceType.weekly:
        if candidate.get("weekday") is None:
            raise HTTPException(
                status_code=422,
                detail="weekly recurrence requires weekday",
            )
        if candidate.get("date") is not None:
            raise HTTPException(
                status_code=422,
                detail="weekly recurrence must not have date",
            )

    elif recurrence_type == RecurrenceType.once:
        if candidate.get("date") is None:
            raise HTTPException(
                status_code=422,
                detail="once recurrence requires date",
            )
        if candidate.get("weekday") is not None:
            raise HTTPException(
                status_code=422,
                detail="once recurrence must not have weekday",
            )


def validate_time_range(candidate: dict) -> None:
    """Raise 422 if start_time equals end_time on the merged candidate."""
    if candidate.get("start_time") == candidate.get("end_time"):
        raise HTTPException(
            status_code=422,
            detail="start_time and end_time must not be equal",
        )


def compute_spans_next_day(candidate: dict) -> bool:
    """Return True when the block crosses midnight (end_time < start_time)."""
    return candidate["end_time"] < candidate["start_time"]


def apply_patch(db_block: FixedBlock, payload: FixedBlockUpdate) -> FixedBlock:
    """Merge payload into db_block, validate the combined state, then mutate.

    Validation order:
      1. validate_recurrence
      2. validate_time_range
      3. compute_spans_next_day
    The ORM object is only written after all checks pass.
    """
    # Build candidate from current DB values
    candidate: dict = {
        "title": db_block.title,
        "recurrence_type": db_block.recurrence_type,
        "weekday": db_block.weekday,
        "date": db_block.date,
        "start_time": db_block.start_time,
        "end_time": db_block.end_time,
    }

    # Overlay only the fields the client explicitly sent
    for field, value in payload.model_dump(exclude_unset=True).items():
        candidate[field] = value

    # Validate combined state — raises HTTPException on failure
    validate_recurrence(candidate)
    validate_time_range(candidate)

    # Derive spans_next_day from merged times
    candidate["spans_next_day"] = compute_spans_next_day(candidate)

    # Write validated values onto ORM object
    for field, value in candidate.items():
        setattr(db_block, field, value)

    return db_block
