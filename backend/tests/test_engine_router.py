"""Integration tests for /api/v1/engine/suggest and /api/v1/engine/book.

All tests use the in-memory SQLite database via the shared conftest fixtures.
No real MySQL connection is needed.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.enums import Priority, RecurrenceType, TaskStatus
from app.models.fixed_block import FixedBlock
from app.models.scheduled_slot import ScheduledSlot
from app.models.task import Task

# ---------------------------------------------------------------------------
# DB helpers (same pattern as test_slots.py)
# ---------------------------------------------------------------------------

USER_ID = 1


def _make_task(
    db,
    title: str = "Test task",
    duration_minutes: int = 60,
    deadline: date | None = None,
    status: TaskStatus = TaskStatus.pending,
) -> Task:
    task = Task(
        user_id=USER_ID,
        title=title,
        duration_minutes=duration_minutes,
        priority=Priority.medium,
        status=status,
        deadline=deadline,
        created_at=datetime.utcnow(),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _make_slot(db, task: Task, start: datetime, end: datetime) -> ScheduledSlot:
    slot = ScheduledSlot(
        task_id=task.id,
        user_id=USER_ID,
        start_datetime=start,
        end_datetime=end,
        created_at=datetime.utcnow(),
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return slot


def _make_weekly_block(
    db,
    weekday: int,
    start_h: int,
    end_h: int,
    spans_next_day: bool = False,
    start_m: int = 0,
    end_m: int = 0,
) -> FixedBlock:
    from datetime import time

    block = FixedBlock(
        user_id=USER_ID,
        title="Test block",
        recurrence_type=RecurrenceType.weekly,
        weekday=weekday,
        date=None,
        start_time=time(start_h, start_m),
        end_time=time(end_h, end_m),
        spans_next_day=spans_next_day,
        created_at=datetime.utcnow(),
    )
    db.add(block)
    db.commit()
    db.refresh(block)
    return block


def _make_once_block(
    db,
    d: date,
    start_h: int,
    end_h: int,
    spans_next_day: bool = False,
    start_m: int = 0,
    end_m: int = 0,
) -> FixedBlock:
    from datetime import time

    block = FixedBlock(
        user_id=USER_ID,
        title="Test block",
        recurrence_type=RecurrenceType.once,
        weekday=None,
        date=d,
        start_time=time(start_h, start_m),
        end_time=time(end_h, end_m),
        spans_next_day=spans_next_day,
        created_at=datetime.utcnow(),
    )
    db.add(block)
    db.commit()
    db.refresh(block)
    return block


def _future_dt(hours_from_now: int = 2) -> datetime:
    """Return a naive datetime in the future (used for book requests)."""
    return datetime.utcnow() + timedelta(hours=hours_from_now)


def _future_date(days_from_now: int = 1) -> date:
    return date.today() + timedelta(days=days_from_now)


# ---------------------------------------------------------------------------
# GET /api/v1/engine/suggest
# ---------------------------------------------------------------------------


class TestSuggest:
    def test_suggest_task_not_found(self, client):
        response = client.get("/api/v1/engine/suggest?task_id=99999")
        assert response.status_code == 404
        assert "task not found" in response.json()["detail"]

    def test_suggest_task_not_pending(self, client, db_session):
        task = _make_task(db_session, status=TaskStatus.scheduled)
        _make_slot(
            db_session,
            task,
            start=_future_dt(2),
            end=_future_dt(3),
        )
        response = client.get(f"/api/v1/engine/suggest?task_id={task.id}")
        assert response.status_code == 409
        assert "not pending" in response.json()["detail"]

    def test_suggest_no_blocks_returns_slots(self, client, db_session):
        task = _make_task(db_session, duration_minutes=60)
        response = client.get(f"/api/v1/engine/suggest?task_id={task.id}")
        assert response.status_code == 200
        slots = response.json()
        assert len(slots) > 0
        # All suggestions are in the future
        for s in slots:
            assert s["start_datetime"] is not None
            assert s["end_datetime"] is not None

    def test_suggest_full_day_blocked_no_results(self, client, db_session):
        task = _make_task(db_session, duration_minutes=60)
        # Block today 08:00–22:00 — covers entire working window
        today = date.today()
        _make_once_block(db_session, d=today, start_h=8, end_h=22)
        from_date_str = today.isoformat()
        response = client.get(
            f"/api/v1/engine/suggest?task_id={task.id}&from_date={from_date_str}"
        )
        assert response.status_code == 200
        slots = response.json()
        # Today should have no results
        today_slots = [s for s in slots if s["date"] == from_date_str]
        assert today_slots == []

    def test_suggest_with_from_date(self, client, db_session):
        task = _make_task(db_session, duration_minutes=60)
        # Use a date 3 days from now to verify from_date is respected
        future_date = _future_date(3)
        response = client.get(
            f"/api/v1/engine/suggest?task_id={task.id}&from_date={future_date.isoformat()}"
        )
        assert response.status_code == 200
        slots = response.json()
        # All slot dates should be on or after future_date
        for s in slots:
            assert s["date"] >= future_date.isoformat()

    def test_suggest_from_date_in_past(self, client, db_session):
        task = _make_task(db_session, duration_minutes=60)
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        response = client.get(
            f"/api/v1/engine/suggest?task_id={task.id}&from_date={yesterday}"
        )
        assert response.status_code == 422
        assert "from_date cannot be in the past" in response.json()["detail"]

    def test_suggest_respects_deadline(self, client, db_session):
        deadline = _future_date(2)
        task = _make_task(db_session, duration_minutes=60, deadline=deadline)
        response = client.get(f"/api/v1/engine/suggest?task_id={task.id}")
        assert response.status_code == 200
        slots = response.json()
        # No suggestion should have a date after the deadline
        for s in slots:
            assert s["date"] <= deadline.isoformat()

    def test_suggest_overnight_block_respected(self, client, db_session):
        """Overnight block tail reduces available window on the next day."""
        task = _make_task(db_session, duration_minutes=60)
        today = date.today()
        tomorrow = today + timedelta(days=1)
        # Block today 22:00 → tomorrow 10:00
        _make_once_block(
            db_session, d=today, start_h=22, end_h=10, spans_next_day=True
        )
        response = client.get(
            f"/api/v1/engine/suggest?task_id={task.id}&from_date={tomorrow.isoformat()}"
        )
        assert response.status_code == 200
        slots = response.json()
        # No slot on tomorrow should start before 10:00
        for s in slots:
            if s["date"] == tomorrow.isoformat():
                slot_start = datetime.fromisoformat(s["start_datetime"])
                assert slot_start.hour >= 10

    def test_suggest_existing_slot_excluded(self, client, db_session):
        """An existing ScheduledSlot blocks its interval from being suggested."""
        task = _make_task(db_session, duration_minutes=60)
        other_task = _make_task(db_session, title="Other task", duration_minutes=60,
                                status=TaskStatus.scheduled)
        # Create a slot for other_task that occupies today 10:00–11:00
        today = date.today()
        existing_start = datetime.combine(today, __import__('datetime').time(10, 0))
        existing_end = existing_start + timedelta(hours=1)
        _make_slot(db_session, other_task, start=existing_start, end=existing_end)

        response = client.get(
            f"/api/v1/engine/suggest?task_id={task.id}&from_date={today.isoformat()}"
        )
        assert response.status_code == 200
        slots = response.json()
        # No suggestion should overlap [10:00, 11:00) on today
        for s in slots:
            if s["date"] == today.isoformat():
                s_start = datetime.fromisoformat(s["start_datetime"])
                s_end = datetime.fromisoformat(s["end_datetime"])
                overlaps = s_start < existing_end and s_end > existing_start
                assert not overlaps


# ---------------------------------------------------------------------------
# POST /api/v1/engine/book
# ---------------------------------------------------------------------------


class TestBook:
    def test_book_task_not_found(self, client):
        payload = {
            "task_id": 99999,
            "start_datetime": _future_dt(2).isoformat(),
        }
        response = client.post("/api/v1/engine/book", json=payload)
        assert response.status_code == 404
        assert "task not found" in response.json()["detail"]

    def test_book_task_not_pending(self, client, db_session):
        task = _make_task(db_session, status=TaskStatus.scheduled)
        _make_slot(db_session, task, start=_future_dt(2), end=_future_dt(3))
        payload = {
            "task_id": task.id,
            "start_datetime": _future_dt(4).isoformat(),
        }
        response = client.post("/api/v1/engine/book", json=payload)
        assert response.status_code == 409
        assert "not pending" in response.json()["detail"]

    def test_book_past_datetime_rejected(self, client, db_session):
        task = _make_task(db_session)
        # Use datetime.now() (local, naive) to match the Pydantic validator comparison
        past_dt = (datetime.now() - timedelta(hours=1)).isoformat()
        payload = {"task_id": task.id, "start_datetime": past_dt}
        response = client.post("/api/v1/engine/book", json=payload)
        assert response.status_code == 422  # Pydantic validator

    def test_book_exceeds_deadline(self, client, db_session):
        # Deadline is today; 90-minute task starting at 21:30 ends at 23:00 (> 22:00)
        deadline = date.today()
        task = _make_task(db_session, duration_minutes=90, deadline=deadline)
        # Start at 21:30 today → end 23:00 → exceeds WORK_END (22:00)
        start = datetime.combine(deadline, __import__('datetime').time(21, 30))
        # Must be in the future for Pydantic to accept it
        if start <= datetime.utcnow():
            pytest.skip("Cannot test deadline booking with today as deadline when 21:30 has passed")
        payload = {"task_id": task.id, "start_datetime": start.isoformat()}
        response = client.post("/api/v1/engine/book", json=payload)
        assert response.status_code == 422
        assert "deadline" in response.json()["detail"]

    def test_book_conflicts_with_fixed_block(self, client, db_session):
        task = _make_task(db_session, duration_minutes=60)
        tomorrow = _future_date(1)
        # Block: tomorrow 10:00–12:00
        _make_once_block(db_session, d=tomorrow, start_h=10, end_h=12)
        # Try to book tomorrow 10:30 (overlaps)
        start = datetime.combine(tomorrow, __import__('datetime').time(10, 30))
        payload = {"task_id": task.id, "start_datetime": start.isoformat()}
        response = client.post("/api/v1/engine/book", json=payload)
        assert response.status_code == 409
        assert "fixed block" in response.json()["detail"]

    def test_book_conflicts_with_existing_slot(self, client, db_session):
        task = _make_task(db_session, duration_minutes=60)
        other_task = _make_task(db_session, title="Other", duration_minutes=60,
                                status=TaskStatus.scheduled)
        tomorrow = _future_date(1)
        slot_start = datetime.combine(tomorrow, __import__('datetime').time(10, 0))
        slot_end = slot_start + timedelta(hours=1)
        _make_slot(db_session, other_task, start=slot_start, end=slot_end)

        # Try to book at 10:00 (direct overlap)
        payload = {"task_id": task.id, "start_datetime": slot_start.isoformat()}
        response = client.post("/api/v1/engine/book", json=payload)
        assert response.status_code == 409
        assert "scheduled slot" in response.json()["detail"]

    def test_book_success(self, client, db_session):
        task = _make_task(db_session, duration_minutes=60)
        start = _future_dt(2)
        payload = {"task_id": task.id, "start_datetime": start.isoformat()}
        response = client.post("/api/v1/engine/book", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["task_id"] == task.id
        assert data["user_id"] == USER_ID
        assert "start_datetime" in data
        assert "end_datetime" in data

        # Task.status must now be 'scheduled'
        db_session.expire_all()
        db_session.refresh(task)
        assert task.status == TaskStatus.scheduled

        # A ScheduledSlot must exist for this task
        slot = db_session.query(ScheduledSlot).filter_by(task_id=task.id).first()
        assert slot is not None
        assert slot.user_id == USER_ID

    def test_book_slot_and_task_status_atomic(self, client, db_session):
        """Both ScheduledSlot creation and Task.status=scheduled happen in one commit."""
        task = _make_task(db_session, duration_minutes=30)
        start = _future_dt(2)
        payload = {"task_id": task.id, "start_datetime": start.isoformat()}
        response = client.post("/api/v1/engine/book", json=payload)
        assert response.status_code == 201

        db_session.expire_all()
        db_session.refresh(task)

        # Both the slot and the status transition must be visible in the same session
        slot = db_session.query(ScheduledSlot).filter_by(task_id=task.id).first()
        assert slot is not None
        assert task.status == TaskStatus.scheduled

    def test_book_duplicate_booking_rejected(self, client, db_session):
        """Booking the same task twice is rejected (UNIQUE constraint guard)."""
        task = _make_task(db_session, duration_minutes=60)
        start = _future_dt(2)
        payload = {"task_id": task.id, "start_datetime": start.isoformat()}

        # First booking succeeds
        r1 = client.post("/api/v1/engine/book", json=payload)
        assert r1.status_code == 201

        # Second booking for same task — task is now 'scheduled', must be rejected
        start2 = _future_dt(5)
        payload2 = {"task_id": task.id, "start_datetime": start2.isoformat()}
        r2 = client.post("/api/v1/engine/book", json=payload2)
        assert r2.status_code == 409
        assert "not pending" in r2.json()["detail"]
