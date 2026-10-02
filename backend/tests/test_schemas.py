"""
Pydantic schema smoke tests for ST-3.

These tests cover only what Pydantic itself validates — individual field
constraints and the one cross-field check that is safe on Create (start_time
!= end_time, because both fields are always present).

Intentionally NOT tested here (deferred to ST-4 router/service tests):
  - recurrence mutual-exclusivity (weekly requires weekday, once requires date)
  - spans_next_day computation (end_time < start_time)
  - end_datetime computation (start_datetime + duration)
"""

from datetime import date, datetime, time, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.schemas.engine import BookRequest, SlotSuggestion
from app.schemas.fixed_block import FixedBlockCreate, FixedBlockRead, FixedBlockUpdate
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate

from app.models.enums import Priority, RecurrenceType, TaskStatus


# ---------------------------------------------------------------------------
# FixedBlockCreate — valid cases
# ---------------------------------------------------------------------------


def test_fixed_block_create_weekly_valid():
    block = FixedBlockCreate(
        title="Faculdade",
        recurrence_type=RecurrenceType.weekly,
        weekday=0,
        start_time=time(8, 0),
        end_time=time(10, 0),
    )
    assert block.title == "Faculdade"
    assert block.weekday == 0


def test_fixed_block_create_once_valid():
    block = FixedBlockCreate(
        title="Consulta",
        recurrence_type=RecurrenceType.once,
        date=date.today() + timedelta(days=1),
        start_time=time(14, 0),
        end_time=time(15, 0),
    )
    assert block.date is not None


# ---------------------------------------------------------------------------
# FixedBlockCreate — invalid cases
# ---------------------------------------------------------------------------


def test_fixed_block_create_weekday_too_high():
    with pytest.raises(ValidationError) as exc_info:
        FixedBlockCreate(
            title="X",
            recurrence_type=RecurrenceType.weekly,
            weekday=7,
            start_time=time(8, 0),
            end_time=time(9, 0),
        )
    assert "weekday" in str(exc_info.value)


def test_fixed_block_create_weekday_negative():
    with pytest.raises(ValidationError) as exc_info:
        FixedBlockCreate(
            title="X",
            recurrence_type=RecurrenceType.weekly,
            weekday=-1,
            start_time=time(8, 0),
            end_time=time(9, 0),
        )
    assert "weekday" in str(exc_info.value)


def test_fixed_block_create_start_equals_end():
    with pytest.raises(ValidationError) as exc_info:
        FixedBlockCreate(
            title="X",
            recurrence_type=RecurrenceType.weekly,
            weekday=1,
            start_time=time(9, 0),
            end_time=time(9, 0),
        )
    assert "start_time" in str(exc_info.value) or "end_time" in str(exc_info.value)


# ---------------------------------------------------------------------------
# FixedBlockUpdate — weekday range validator still applies
# ---------------------------------------------------------------------------


def test_fixed_block_update_weekday_out_of_range():
    with pytest.raises(ValidationError) as exc_info:
        FixedBlockUpdate(weekday=7)
    assert "weekday" in str(exc_info.value)


def test_fixed_block_update_all_optional_empty():
    # An empty PATCH payload is valid — the router will merge it with the DB record.
    update = FixedBlockUpdate()
    assert update.title is None
    assert update.weekday is None


# ---------------------------------------------------------------------------
# FixedBlockRead — from_attributes round-trip
# ---------------------------------------------------------------------------


def test_fixed_block_read_from_attributes():
    class FakeORM:
        id = 1
        user_id = 1
        title = "Work"
        recurrence_type = RecurrenceType.weekly
        weekday = 2
        date = None
        start_time = time(9, 0)
        end_time = time(17, 0)
        spans_next_day = False
        created_at = datetime(2024, 1, 1, 12, 0)

    read = FixedBlockRead.model_validate(FakeORM())
    assert read.spans_next_day is False
    assert read.weekday == 2


# ---------------------------------------------------------------------------
# TaskCreate — valid cases
# ---------------------------------------------------------------------------


def test_task_create_valid_minimal():
    task = TaskCreate(title="Study", duration_minutes=60)
    assert task.priority == Priority.medium
    assert task.deadline is None


def test_task_create_deadline_today():
    task = TaskCreate(title="Study", duration_minutes=30, deadline=date.today())
    assert task.deadline == date.today()


def test_task_create_deadline_future():
    task = TaskCreate(
        title="Study", duration_minutes=30, deadline=date.today() + timedelta(days=3)
    )
    assert task.deadline is not None


# ---------------------------------------------------------------------------
# TaskCreate — invalid cases
# ---------------------------------------------------------------------------


def test_task_create_duration_zero():
    with pytest.raises(ValidationError) as exc_info:
        TaskCreate(title="X", duration_minutes=0)
    assert "duration_minutes" in str(exc_info.value)


def test_task_create_duration_negative():
    with pytest.raises(ValidationError) as exc_info:
        TaskCreate(title="X", duration_minutes=-5)
    assert "duration_minutes" in str(exc_info.value)


def test_task_create_deadline_in_the_past():
    with pytest.raises(ValidationError) as exc_info:
        TaskCreate(title="X", duration_minutes=30, deadline=date.today() - timedelta(days=1))
    assert "deadline" in str(exc_info.value)


# ---------------------------------------------------------------------------
# TaskUpdate — duration validator still applies when field is present
# ---------------------------------------------------------------------------


def test_task_update_duration_zero():
    with pytest.raises(ValidationError) as exc_info:
        TaskUpdate(duration_minutes=0)
    assert "duration_minutes" in str(exc_info.value)


def test_task_update_all_optional_empty():
    update = TaskUpdate()
    assert update.title is None
    assert update.duration_minutes is None


def test_task_update_has_no_status_field():
    # status must not be accepted — it is managed via engine actions only.
    update = TaskUpdate(title="New title")
    assert not hasattr(update, "status") or update.model_fields.get("status") is None


# ---------------------------------------------------------------------------
# TaskRead — status is present; from_attributes round-trip
# ---------------------------------------------------------------------------


def test_task_read_from_attributes():
    class FakeORM:
        id = 1
        user_id = 1
        title = "Study"
        duration_minutes = 60
        deadline = None
        priority = Priority.high
        status = TaskStatus.pending
        created_at = datetime(2024, 1, 1, 12, 0)

    read = TaskRead.model_validate(FakeORM())
    assert read.status == TaskStatus.pending
    assert read.priority == Priority.high


# ---------------------------------------------------------------------------
# BookRequest — valid / invalid
# ---------------------------------------------------------------------------


def test_book_request_future_naive():
    future = datetime.now() + timedelta(hours=2)
    req = BookRequest(task_id=1, start_datetime=future)
    assert req.task_id == 1


def test_book_request_future_aware():
    future = datetime.now(tz=timezone.utc) + timedelta(hours=2)
    req = BookRequest(task_id=1, start_datetime=future)
    assert req.task_id == 1


def test_book_request_past_raises():
    past = datetime.now() - timedelta(hours=1)
    with pytest.raises(ValidationError) as exc_info:
        BookRequest(task_id=1, start_datetime=past)
    assert "start_datetime" in str(exc_info.value)


# ---------------------------------------------------------------------------
# SlotSuggestion — basic construction
# ---------------------------------------------------------------------------


def test_slot_suggestion_valid():
    s = SlotSuggestion(
        start_datetime=datetime(2025, 6, 10, 9, 0),
        end_datetime=datetime(2025, 6, 10, 10, 30),
        date=date(2025, 6, 10),
    )
    assert s.date == date(2025, 6, 10)
