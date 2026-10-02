"""Router tests for /api/v1/slots.

Slot creation uses db_session directly because POST /engine/book is not
yet implemented (reserved for ST-5).  This mirrors what the engine will do
without coupling these tests to unimplemented code.
"""

from datetime import datetime, timedelta, timezone

from app.models.enums import Priority, TaskStatus
from app.models.scheduled_slot import ScheduledSlot
from app.models.task import Task


def _make_task(db, title="Test task", duration_minutes=60) -> Task:
    """Create and persist a Task directly via db_session."""
    task = Task(
        user_id=1,
        title=title,
        duration_minutes=duration_minutes,
        priority=Priority.medium,
        status=TaskStatus.scheduled,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _make_slot(db, task: Task) -> ScheduledSlot:
    """Create and persist a ScheduledSlot directly via db_session."""
    start = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
    end = start + timedelta(minutes=task.duration_minutes)
    slot = ScheduledSlot(
        task_id=task.id,
        user_id=1,
        start_datetime=start,
        end_datetime=end,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return slot


# ---------------------------------------------------------------------------
# GET /api/v1/slots
# ---------------------------------------------------------------------------

def test_list_slots_empty(client):
    response = client.get("/api/v1/slots/")
    assert response.status_code == 200
    assert response.json() == []


def test_list_slots_returns_created_slot(client, db_session):
    task = _make_task(db_session)
    slot = _make_slot(db_session, task)

    response = client.get("/api/v1/slots/")
    assert response.status_code == 200
    slots = response.json()
    assert len(slots) == 1
    assert slots[0]["id"] == slot.id
    assert slots[0]["task_id"] == task.id


# ---------------------------------------------------------------------------
# GET /api/v1/slots/{id}
# ---------------------------------------------------------------------------

def test_get_slot_found(client, db_session):
    task = _make_task(db_session)
    slot = _make_slot(db_session, task)

    response = client.get(f"/api/v1/slots/{slot.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == slot.id
    assert data["task_id"] == task.id
    assert data["user_id"] == 1


def test_get_slot_not_found(client):
    response = client.get("/api/v1/slots/99999")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/v1/slots/{id}
# ---------------------------------------------------------------------------

def test_delete_slot_resets_task_to_pending(client, db_session):
    """DELETE /slots/{id} must atomically reset the related task status to pending."""
    task = _make_task(db_session)
    slot = _make_slot(db_session, task)
    slot_id = slot.id  # capture before the ORM object becomes detached/deleted

    assert task.status == TaskStatus.scheduled

    response = client.delete(f"/api/v1/slots/{slot_id}")
    assert response.status_code == 204

    # Expire the cached state and reload from DB
    db_session.expire_all()
    db_session.refresh(task)
    assert task.status == TaskStatus.pending

    # Slot must be gone
    response = client.get(f"/api/v1/slots/{slot_id}")
    assert response.status_code == 404


def test_delete_slot_not_found(client):
    response = client.delete("/api/v1/slots/99999")
    assert response.status_code == 404
