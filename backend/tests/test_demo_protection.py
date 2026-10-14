"""Public demo protections: required session id, global daily AI cap, per-visitor item limits.

All of them are off by default; each test turns one on through the settings object.
"""

from __future__ import annotations

import json

import pytest

from app.ai.provider import CappedProvider, MockProvider, ProviderError, get_provider
from app.core.session import BLOCK_LIMIT_DETAIL, SESSION_REQUIRED_DETAIL, TASK_LIMIT_DETAIL
from app.core.settings import settings
from app.main import app

pytestmark = pytest.mark.usefixtures("fixed_now")

H_A = {"X-Session-Id": "visitor-one-session-id"}
H_B = {"X-Session-Id": "visitor-two-session-id"}

_VALID = json.dumps({"recommended_candidate_id": 0, "explanation": "First available slot selected."})


@pytest.fixture()
def mock_provider():
    provider = MockProvider(fixed_response=_VALID)
    app.dependency_overrides[get_provider] = lambda: provider
    yield provider
    del app.dependency_overrides[get_provider]


def _task(client, headers=None, title="Task"):
    return client.post("/api/v1/tasks/", json={"title": title, "duration_minutes": 60, "priority": "medium"},
                       headers=headers or {})


def _block(client, headers=None):
    return client.post(
        "/api/v1/blocks/",
        json={"title": "Block", "recurrence_type": "weekly", "weekday": 0,
              "start_time": "09:00:00", "end_time": "10:00:00"},
        headers=headers or {},
    )


class TestRequireSession:
    def test_header_is_required_when_enabled(self, client, monkeypatch):
        monkeypatch.setattr(settings, "REQUIRE_SESSION", True)
        response = client.get("/api/v1/tasks/")
        assert response.status_code == 400
        assert response.json()["detail"] == SESSION_REQUIRED_DETAIL
        assert client.post("/api/v1/tasks/", json={"title": "x", "duration_minutes": 60}).status_code == 400
        assert client.get("/api/v1/tasks/", headers=H_A).status_code == 200

    def test_health_stays_public(self, client, monkeypatch):
        monkeypatch.setattr(settings, "REQUIRE_SESSION", True)
        assert client.get("/health").status_code == 200

    def test_default_user_still_works_when_disabled(self, client):
        assert client.get("/api/v1/tasks/").status_code == 200


class TestGlobalAiCap:
    def test_capped_provider_never_calls_the_model_and_keeps_the_audit_identity(self):
        inner = MockProvider(fixed_response=_VALID)
        capped = CappedProvider(inner)
        assert (capped.provider_name, capped.model_id) == (inner.provider_name, inner.model_id)
        with pytest.raises(ProviderError):
            capped.complete("prompt")

    def test_after_the_cap_recommendations_use_the_deterministic_fallback(self, client, mock_provider, monkeypatch):
        monkeypatch.setattr(settings, "AI_DAILY_CAP", 2)
        task = _task(client).json()

        results = [client.post("/api/v1/planner/recommend", json={"task_id": task["id"]}).json() for _ in range(4)]

        assert [r["fallback_used"] for r in results] == [False, False, True, True]
        for capped in results[2:]:
            assert capped["reason_codes"] == ["PROVIDER_FALLBACK"]
            assert capped["recommended_slot"]["start_datetime"] == capped["candidate_slots"][0]["start_datetime"]

    def test_cap_applies_across_visitors(self, client, mock_provider, monkeypatch):
        monkeypatch.setattr(settings, "AI_DAILY_CAP", 1)
        task_a = _task(client, H_A).json()
        task_b = _task(client, H_B).json()
        first = client.post("/api/v1/planner/recommend", json={"task_id": task_a["id"]}, headers=H_A).json()
        second = client.post("/api/v1/planner/recommend", json={"task_id": task_b["id"]}, headers=H_B).json()
        assert first["fallback_used"] is False
        assert second["fallback_used"] is True

    def test_no_cap_by_default(self, client, mock_provider):
        task = _task(client).json()
        for _ in range(3):
            assert client.post("/api/v1/planner/recommend", json={"task_id": task["id"]}).json()["fallback_used"] is False


class TestItemLimits:
    def test_task_limit_per_visitor(self, client, monkeypatch):
        monkeypatch.setattr(settings, "MAX_TASKS_PER_VISITOR", 2)
        assert _task(client, H_A).status_code == 201
        assert _task(client, H_A).status_code == 201
        blocked = _task(client, H_A)
        assert blocked.status_code == 429
        assert blocked.json()["detail"] == TASK_LIMIT_DETAIL
        assert _task(client, H_B).status_code == 201  # other visitors are unaffected

    def test_block_limit_per_visitor(self, client, monkeypatch):
        monkeypatch.setattr(settings, "MAX_BLOCKS_PER_VISITOR", 1)
        assert _block(client, H_A).status_code == 201
        blocked = _block(client, H_A)
        assert blocked.status_code == 429
        assert blocked.json()["detail"] == BLOCK_LIMIT_DETAIL
        assert _block(client, H_B).status_code == 201

    def test_default_user_is_exempt_and_zero_means_unlimited(self, client, monkeypatch):
        monkeypatch.setattr(settings, "MAX_TASKS_PER_VISITOR", 1)
        for _ in range(3):
            assert _task(client).status_code == 201
        monkeypatch.setattr(settings, "MAX_TASKS_PER_VISITOR", 0)
        for _ in range(3):
            assert _task(client, H_A).status_code == 201

    def test_deleting_frees_a_slot(self, client, monkeypatch):
        monkeypatch.setattr(settings, "MAX_TASKS_PER_VISITOR", 1)
        created = _task(client, H_A).json()
        assert _task(client, H_A).status_code == 429
        assert client.delete(f"/api/v1/tasks/{created['id']}", headers=H_A).status_code == 204
        assert _task(client, H_A).status_code == 201
