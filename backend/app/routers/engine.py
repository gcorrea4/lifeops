"""Engine router — GET /engine/suggest and POST /engine/book."""

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.database import get_db
from app.models.fixed_block import FixedBlock
from app.models.scheduled_slot import ScheduledSlot
from app.models.task import Task, TaskStatus
from app.schemas.engine import BookRequest, SlotSuggestion
from app.schemas.scheduled_slot import ScheduledSlotRead
from app.services.engine import (
    block_to_interval,
    blocks_for_day,
    overnight_blocks_from_previous_day,
    overnight_tail_interval,
    suggest_slots,
)

router = APIRouter(prefix="/engine", tags=["engine"])

USER_ID = 1  # hardcoded for Week 1 MVP

LOOKAHEAD_DAYS = 7


def _get_task_or_404(task_id: int, db: Session) -> Task:
    task = (
        db.query(Task)
        .filter(Task.id == task_id, Task.user_id == USER_ID)
        .first()
    )
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task


def _intervals_overlap(
    a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime
) -> bool:
    """Return True when [a_start, a_end) and [b_start, b_end) overlap."""
    return a_start < b_end and b_start < a_end


# ---------------------------------------------------------------------------
# GET /engine/suggest
# ---------------------------------------------------------------------------


@router.get("/suggest", response_model=list[SlotSuggestion])
def suggest(
    task_id: int = Query(...),
    from_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[SlotSuggestion]:
    """Return up to 10 candidate slots for a pending task."""

    # 1. Load task
    task = _get_task_or_404(task_id, db)

    # 2. Task must be pending
    if task.status != TaskStatus.pending:
        raise HTTPException(status_code=409, detail="task is not pending")

    # 3. Resolve from_date — default today, reject past
    resolved_from = from_date if from_date is not None else date.today()
    if resolved_from < date.today():
        raise HTTPException(
            status_code=422, detail="from_date cannot be in the past"
        )

    # 4. Load all FixedBlocks for user
    blocks = db.query(FixedBlock).filter(FixedBlock.user_id == USER_ID).all()

    # 5. Load ScheduledSlots in the lookahead window (+1 day for overnight overflow)
    window_start = datetime.combine(resolved_from, settings.WORK_START)
    window_end = datetime.combine(
        resolved_from + timedelta(days=LOOKAHEAD_DAYS + 1),
        settings.WORK_END,
    )
    slots = (
        db.query(ScheduledSlot)
        .filter(
            ScheduledSlot.user_id == USER_ID,
            ScheduledSlot.start_datetime < window_end,
            ScheduledSlot.end_datetime > window_start,
        )
        .all()
    )

    # 6. Delegate to pure engine service
    return suggest_slots(
        task=task,
        blocks=blocks,
        slots=slots,
        from_date=resolved_from,
        lookahead_days=LOOKAHEAD_DAYS,
        work_start=settings.WORK_START,
        work_end=settings.WORK_END,
    )


# ---------------------------------------------------------------------------
# POST /engine/book
# ---------------------------------------------------------------------------


@router.post("/book", response_model=ScheduledSlotRead, status_code=201)
def book(payload: BookRequest, db: Session = Depends(get_db)) -> ScheduledSlot:
    """Validate and confirm a booking. Revalidates availability at booking time."""

    # 1. Load task
    task = _get_task_or_404(payload.task_id, db)

    # 2. Task must be pending
    if task.status != TaskStatus.pending:
        raise HTTPException(status_code=409, detail="task is not pending")

    # 3. Compute end_datetime server-side
    start_dt = payload.start_datetime
    # Strip timezone info for consistent naive datetime arithmetic
    if start_dt.tzinfo is not None:
        start_dt = start_dt.replace(tzinfo=None)

    # Guard: start_datetime must be in the future (Pydantic validator only fires
    # for Python datetime objects, not for JSON strings; enforce here for HTTP requests)
    if start_dt <= datetime.now():
        raise HTTPException(
            status_code=422, detail="start_datetime must be in the future"
        )

    end_dt = start_dt + timedelta(minutes=task.duration_minutes)

    # 4. Validate deadline (inclusive — end_dt <= combine(deadline, WORK_END))
    if task.deadline is not None:
        deadline_ceiling = datetime.combine(task.deadline, settings.WORK_END)
        if end_dt > deadline_ceiling:
            raise HTTPException(
                status_code=422, detail="slot would exceed task deadline"
            )

    # 5. Load all FixedBlocks for user and revalidate conflicts
    blocks = db.query(FixedBlock).filter(FixedBlock.user_id == USER_ID).all()

    booking_day = start_dt.date()
    for block in blocks:
        # Collect intervals this block produces on the booking day
        relevant_intervals = []
        if block in blocks_for_day(blocks, booking_day):
            relevant_intervals.append(block_to_interval(block, booking_day))
        if block in overnight_blocks_from_previous_day(blocks, booking_day):
            relevant_intervals.append(overnight_tail_interval(block, booking_day))

        for b_start, b_end in relevant_intervals:
            if _intervals_overlap(start_dt, end_dt, b_start, b_end):
                raise HTTPException(
                    status_code=409,
                    detail="slot conflicts with a fixed block",
                )

    # 6. Revalidate ScheduledSlot conflicts
    conflict = (
        db.query(ScheduledSlot)
        .filter(
            ScheduledSlot.user_id == USER_ID,
            ScheduledSlot.start_datetime < end_dt,
            ScheduledSlot.end_datetime > start_dt,
        )
        .first()
    )
    if conflict is not None:
        raise HTTPException(
            status_code=409,
            detail="slot conflicts with an existing scheduled slot",
        )

    # 7–9. Create ScheduledSlot + update Task.status atomically
    slot = ScheduledSlot(
        task_id=task.id,
        user_id=USER_ID,
        start_datetime=start_dt,
        end_datetime=end_dt,
    )
    task.status = TaskStatus.scheduled
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return slot
