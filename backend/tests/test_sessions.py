"""Per-visitor data separation: X-Session-Id isolation, daily recommendation limit, expiry purge.

Everything runs on the in-memory SQLite database from conftest; no network and no real provider.
"""

from __future__ import annotations

import json
from datetime import datetime, time, timedelta, timezone

import pytest

from app.ai.provider import MockProvider, get_provider
from app.core import clock
from app.core.session import (
    DAILY_RECOMMENDATION_LIMIT,
    DEFAULT_USER_ID,
    RATE_LIMIT_DETAIL,
    purge_expired,
    user_id_from_session,
)
from app.main import app
from app.models.enums import Priority, RecurrenceType, TaskStatus
from app.models.fixed_block import FixedBlock
from app.models.scheduled_slot import ScheduledSlot
from app.models.task import Task

pytestmark = pytest.mark.usefixtures("fixed_now")

SESSION_A = "visitor-one-session-id"
SESSION_B = "visitor-two-session-id"
H_A = {"X-Session-Id": SESSION_A}
H_B = {"X-Session-Id": SESSION_B}

_VALID_MOCK_RESPONSE = json.dumps(
    {"recommended_candidate_id": 0, "explanation": "First available slot selected."}
)


@pytest.fixture()
def mock_provider():
    provider = MockProvider(fixed_response=_VALID_MOCK_RESPONSE)
    app.dependency_overrides[get_provider] = lambda: provider
    yield provider
    del app.dependency_overrides[get_provider]


def _create_task(client, headers=None, title="Task"):
    response = client.post(
        "/api/v1/tasks/",
        json={"title": title, "duration_minutes": 60, "priority": "medium"},
        headers=headers or {},
    )
    assert response.status_code == 201
    return response.json()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TestSessionIdMapping:
    def test_user_id_is_stable_positive_and_never_default(self):
        first = user_id_from_session(SESSION_A)
        assert first == user_id_from_session(SESSION_A)
        assert user_id_from_session(SESSION_B) != first
        for session in (SESSION_A, SESSION_B, "x" * 16, "Z" * 64):
            assert 2 <= user_id_from_session(session) < 2**31

    @pytest.mark.parametrize("bad", ["short", "has space in it!!", "a" * 65, "slash/in/session-id-123"])
    def test_invalid_session_id_is_rejected(self, client, bad):
        response = client.get("/api/v1/tasks/", headers={"X-Session-Id": bad})
        assert response.status_code == 400

    def test_missing_header_uses_default_user(self, client):
        created = _create_task(client)
        assert created["user_id"] == DEFAULT_USER_ID


class TestIsolation:
    def test_visitors_only_see_their_own_tasks_and_blocks(self, client):
        task_a = _create_task(client, H_A, "A task")
        block_response = client.post(
            "/api/v1/blocks/",
            json={"title": "A block", "recurrence_type": "weekly", "weekday": 0,
                  "start_time": "09:00:00", "end_time": "10:00:00"},
            headers=H_A,
        )
        assert block_response.status_code == 201
        block_id = block_response.json()["id"]

        assert [t["id"] for t in client.get("/api/v1/tasks/", headers=H_A).json()] == [task_a["id"]]
        assert client.get("/api/v1/tasks/", headers=H_B).json() == []
        assert client.get("/api/v1/tasks/").json() == []
        assert client.get("/api/v1/blocks/", headers=H_B).json() == []

        assert client.get(f"/api/v1/tasks/{task_a['id']}", headers=H_B).status_code == 404
        assert client.patch(f"/api/v1/tasks/{task_a['id']}", json={"title": "hijack"}, headers=H_B).status_code == 404
        assert client.delete(f"/api/v1/tasks/{task_a['id']}", headers=H_B).status_code == 404
        assert client.get(f"/api/v1/blocks/{block_id}", headers=H_B).status_code == 404
        assert client.delete(f"/api/v1/blocks/{block_id}", headers=H_B).status_code == 404
        # The owner still has everything.
        assert client.get(f"/api/v1/tasks/{task_a['id']}", headers=H_A).json()["title"] == "A task"

    def test_default_user_data_is_not_visible_to_visitors(self, client):
        _create_task(client, None, "Default user task")
        assert client.get("/api/v1/tasks/", headers=H_A).json() == []
        assert len(client.get("/api/v1/tasks/").json()) == 1

    def test_booking_and_slots_are_isolated(self, client):
        task_a = _create_task(client, H_A)
        booked = client.post(
            "/api/v1/engine/book",
            json={"task_id": task_a["id"], "start_datetime": "2026-10-08T10:00:00"},
            headers=H_A,
        )
        assert booked.status_code == 201
        slot_id = booked.json()["id"]

        assert len(client.get("/api/v1/slots/", headers=H_A).json()) == 1
        assert client.get("/api/v1/slots/", headers=H_B).json() == []
        assert client.get(f"/api/v1/slots/{slot_id}", headers=H_B).status_code == 404
        assert client.delete(f"/api/v1/slots/{slot_id}", headers=H_B).status_code == 404
        # Another visitor cannot book or plan someone else's task.
        other = client.post(
            "/api/v1/engine/book",
            json={"task_id": task_a["id"], "start_datetime": "2026-10-08T14:00:00"},
            headers=H_B,
        )
        assert other.status_code == 404
        assert client.get(f"/api/v1/engine/suggest?task_id={task_a['id']}", headers=H_B).status_code == 404

    def test_one_visitors_commitment_does_not_block_another(self, client):
        client.post(
            "/api/v1/blocks/",
            json={"title": "Busy", "recurrence_type": "once", "date": "2026-10-08",
                  "start_time": "09:00:00", "end_time": "18:00:00"},
            headers=H_A,
        )
        task_b = _create_task(client, H_B)
        booked = client.post(
            "/api/v1/engine/book",
            json={"task_id": task_b["id"], "start_datetime": "2026-10-08T10:00:00"},
            headers=H_B,
        )
        assert booked.status_code == 201

    def test_recommendation_and_decision_are_isolated(self, client, mock_provider):
        task_a = _create_task(client, H_A)
        recommended = client.post("/api/v1/planner/recommend", json={"task_id": task_a["id"]}, headers=H_A)
        assert recommended.status_code == 201
        rec_id = recommended.json()["recommendation_id"]

        # Another visitor can neither plan the task nor decide on the recommendation.
        assert client.post("/api/v1/planner/recommend", json={"task_id": task_a["id"]}, headers=H_B).status_code == 404
        assert client.post("/api/v1/planner/decision", json={"recommendation_id": rec_id, "action": "REJECTED"},
                           headers=H_B).status_code == 404
        assert client.post("/api/v1/planner/decision", json={"recommendation_id": rec_id, "action": "APPROVED"},
                           headers=H_A).status_code == 200


class TestRecommendationLimit:
    def test_visitor_is_limited_per_day_and_others_are_not_affected(self, client, mock_provider):
        task_a = _create_task(client, H_A)
        for _ in range(DAILY_RECOMMENDATION_LIMIT):
            assert client.post("/api/v1/planner/recommend", json={"task_id": task_a["id"]}, headers=H_A).status_code == 201

        blocked = client.post("/api/v1/planner/recommend", json={"task_id": task_a["id"]}, headers=H_A)
        assert blocked.status_code == 429
        assert blocked.json()["detail"] == RATE_LIMIT_DETAIL

        task_b = _create_task(client, H_B)
        assert client.post("/api/v1/planner/recommend", json={"task_id": task_b["id"]}, headers=H_B).status_code == 201

    def test_default_user_is_exempt(self, client, mock_provider):
        task = _create_task(client)
        for _ in range(DAILY_RECOMMENDATION_LIMIT + 2):
            assert client.post("/api/v1/planner/recommend", json={"task_id": task["id"]}).status_code == 201


class TestPurge:
    def _task(self, db, user_id, age_hours, title):
        task = Task(user_id=user_id, title=title, duration_minutes=60, priority=Priority.medium,
                    status=TaskStatus.pending, created_at=_utc_now() - timedelta(hours=age_hours))
        db.add(task)
        db.commit()
        db.refresh(task)
        return task

    def test_purge_removes_only_expired_visitor_data(self, db_session):
        old_visitor = self._task(db_session, 5, 30, "old visitor task")
        fresh_visitor = self._task(db_session, 5, 1, "fresh visitor task")
        old_default = self._task(db_session, DEFAULT_USER_ID, 300, "old default task")
        db_session.add(ScheduledSlot(task_id=old_visitor.id, user_id=5,
                                     start_datetime=datetime(2026, 10, 8, 10), end_datetime=datetime(2026, 10, 8, 11)))
        db_session.add(FixedBlock(user_id=5, title="old block", recurrence_type=RecurrenceType.weekly, weekday=1,
                                  start_time=time(9), end_time=time(10), spans_next_day=False,
                                  created_at=_utc_now() - timedelta(hours=40)))
        db_session.commit()

        deleted = purge_expired(db_session, force=True)

        assert deleted == 2  # the expired task and the expired commitment
        remaining = {t.title for t in db_session.query(Task).all()}
        assert remaining == {"fresh visitor task", "old default task"}
        assert db_session.query(ScheduledSlot).count() == 0  # cascaded with its task
        assert db_session.query(FixedBlock).count() == 0
        assert fresh_visitor.id and old_default.id

    def test_purge_is_rate_limited_unless_forced(self, db_session):
        self._task(db_session, 5, 30, "old visitor task")
        assert purge_expired(db_session, force=True) == 1
        self._task(db_session, 5, 30, "another old task")
        assert purge_expired(db_session) == 0  # ran moments ago, skipped
        assert purge_expired(db_session, force=True) == 1

    def test_creating_data_triggers_cleanup_without_breaking_the_request(self, client, db_session):
        self._task(db_session, 5, 30, "old visitor task")
        purge_expired(db_session, now=_utc_now() - timedelta(hours=2), force=True)  # reset the interval clock
        created = _create_task(client, H_A, "new task")
        assert created["title"] == "new task"
