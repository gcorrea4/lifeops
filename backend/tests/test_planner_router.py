"""Integration tests for POST /api/v1/planner/recommend and POST /api/v1/planner/decision.

All tests use:
- The shared in-memory SQLite database via conftest fixtures.
- A MockProvider dependency override so no real watsonx credentials are required.
- Standard conftest db_session + client fixtures for isolation and cleanup.
"""

from __future__ import annotations

import json
from datetime import date, datetime

import pytest
from app.core import clock

pytestmark = pytest.mark.usefixtures("fixed_now")

from app.ai.provider import MockProvider, get_provider
from app.main import app
from app.models.ai_recommendation import AIRecommendation
from app.models.enums import Priority, TaskStatus
from app.models.task import Task

USER_ID = 1

# A valid MockProvider response that PlannerAgent._parse_response() will accept.
_VALID_MOCK_RESPONSE = json.dumps(
    {
        "recommended_candidate_id": 0,
        "reason_codes": ["EARLIEST_SLOT"],
        "explanation": "First available slot selected.",
    }
)

# An invalid response that will trigger the deterministic fallback.
_INVALID_MOCK_RESPONSE = "not json at all"


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


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
        created_at=clock.now(),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


# ---------------------------------------------------------------------------
# Provider fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_provider(request):
    """Override get_provider with a MockProvider; tear down after the test.

    Accepts an optional indirect parameter to supply a custom fixed_response.
    Default is _VALID_MOCK_RESPONSE.
    """
    fixed_response = getattr(request, "param", _VALID_MOCK_RESPONSE)
    provider = MockProvider(fixed_response=fixed_response)
    app.dependency_overrides[get_provider] = lambda: provider
    yield provider
    del app.dependency_overrides[get_provider]


# ---------------------------------------------------------------------------
# TestRecommend
# ---------------------------------------------------------------------------


class TestRecommend:
    """Tests for POST /api/v1/planner/recommend."""

    def test_recommend_returns_201(self, client, db_session, mock_provider):
        task = _make_task(db_session)
        response = client.post(
            "/api/v1/planner/recommend", json={"task_id": task.id}
        )
        assert response.status_code == 201
        body = response.json()
        assert "recommendation_id" in body
        assert body["task_id"] == task.id
        assert "recommended_slot" in body
        assert "start_datetime" in body["recommended_slot"]
        assert "end_datetime" in body["recommended_slot"]
        assert isinstance(body["reason_codes"], list)
        assert len(body["reason_codes"]) > 0
        assert isinstance(body["explanation"], str)
        assert isinstance(body["candidate_slots"], list)
        assert len(body["candidate_slots"]) > 0
        assert isinstance(body["fallback_used"], bool)

    def test_recommend_persists_audit_row(self, client, db_session, mock_provider):
        task = _make_task(db_session)
        response = client.post(
            "/api/v1/planner/recommend", json={"task_id": task.id}
        )
        assert response.status_code == 201
        rec_id = response.json()["recommendation_id"]

        rec = db_session.query(AIRecommendation).filter(AIRecommendation.id == rec_id).first()
        assert rec is not None
        assert rec.task_id == task.id
        assert rec.user_id == USER_ID
        assert rec.candidate_slots_json is not None
        candidates = json.loads(rec.candidate_slots_json)
        assert len(candidates) > 0
        assert rec.recommended_start is not None
        assert rec.recommended_end is not None
        reason_codes = json.loads(rec.reason_codes)
        assert isinstance(reason_codes, list)
        assert len(reason_codes) > 0
        # user_action must be null — no decision yet
        assert rec.user_action is None
        assert rec.final_start is None
        assert rec.final_end is None

    def test_recommend_candidate_slots_in_response_match_persisted(
        self, client, db_session, mock_provider
    ):
        """The candidate_slots in the response must be identical to what was stored."""
        task = _make_task(db_session)
        response = client.post(
            "/api/v1/planner/recommend", json={"task_id": task.id}
        )
        assert response.status_code == 201
        body = response.json()
        rec_id = body["recommendation_id"]

        rec = db_session.query(AIRecommendation).filter(AIRecommendation.id == rec_id).first()
        stored_candidates = json.loads(rec.candidate_slots_json)

        # Number of candidates must match
        assert len(body["candidate_slots"]) == len(stored_candidates)

        # Each slot in the response must correspond to a stored slot
        for resp_slot, stored_slot in zip(body["candidate_slots"], stored_candidates):
            # Compare ISO strings — stored as full ISO, response serialised the same way
            assert resp_slot["start_datetime"].replace("Z", "+00:00").rstrip("0").rstrip(".") in \
                stored_slot["start_datetime"].rstrip("0").rstrip(".") or \
                stored_slot["start_datetime"].startswith(resp_slot["start_datetime"][:16])

    def test_recommend_fallback_used_flag_on_invalid_provider_response(
        self, client, db_session
    ):
        """When the provider returns invalid JSON the agent falls back and sets fallback_used=True."""
        provider = MockProvider(fixed_response=_INVALID_MOCK_RESPONSE)
        app.dependency_overrides[get_provider] = lambda: provider
        try:
            task = _make_task(db_session)
            response = client.post(
                "/api/v1/planner/recommend", json={"task_id": task.id}
            )
            assert response.status_code == 201
            assert response.json()["fallback_used"] is True
        finally:
            del app.dependency_overrides[get_provider]

    def test_recommend_task_not_found(self, client, db_session, mock_provider):
        response = client.post(
            "/api/v1/planner/recommend", json={"task_id": 99999}
        )
        assert response.status_code == 404
        assert "task not found" in response.json()["detail"]

    def test_recommend_task_not_pending(self, client, db_session, mock_provider):
        task = _make_task(db_session, status=TaskStatus.scheduled)
        response = client.post(
            "/api/v1/planner/recommend", json={"task_id": task.id}
        )
        assert response.status_code == 409
        assert "not pending" in response.json()["detail"]

    def test_recommend_no_slots_available(self, client, db_session, mock_provider):
        """A task with a past deadline produces no candidates → 422."""
        from datetime import timedelta
        past_deadline = clock.now().date() - timedelta(days=1)
        # Create with deadline in the past — bypass Pydantic validator by writing directly
        task = Task(
            user_id=USER_ID,
            title="Overdue task",
            duration_minutes=60,
            priority=Priority.medium,
            status=TaskStatus.pending,
            deadline=past_deadline,
            created_at=clock.now(),
        )
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        response = client.post(
            "/api/v1/planner/recommend", json={"task_id": task.id}
        )
        assert response.status_code == 422
        assert "no candidate slots" in response.json()["detail"]


# ---------------------------------------------------------------------------
# TestDecision
# ---------------------------------------------------------------------------


class TestDecision:
    """Tests for POST /api/v1/planner/decision."""

    def _make_recommendation(self, client, db_session):
        """Helper: create a task and call /recommend to get a persisted recommendation."""
        task = _make_task(db_session)
        response = client.post(
            "/api/v1/planner/recommend", json={"task_id": task.id}
        )
        assert response.status_code == 201
        return response.json()

    def test_decision_approved(self, client, db_session, mock_provider):
        rec_body = self._make_recommendation(client, db_session)
        rec_id = rec_body["recommendation_id"]

        response = client.post(
            "/api/v1/planner/decision",
            json={"recommendation_id": rec_id, "action": "APPROVED"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["recommendation_id"] == rec_id
        assert body["action"] == "APPROVED"
        assert body["final_start"] is not None
        assert body["final_end"] is not None
        assert "engine/book" in body["message"]

        # Verify final_start matches recommended_start in the DB row
        rec = db_session.query(AIRecommendation).filter(AIRecommendation.id == rec_id).first()
        db_session.refresh(rec)
        assert rec.user_action.value == "APPROVED"
        assert rec.final_start == rec.recommended_start
        assert rec.final_end == rec.recommended_end

    def test_decision_approved_ignores_chosen_slot(self, client, db_session, mock_provider):
        """APPROVED ignores any chosen_start/end — final slot must equal recommended."""
        rec_body = self._make_recommendation(client, db_session)
        rec_id = rec_body["recommendation_id"]

        # Supply an invented datetime — it must be silently ignored
        response = client.post(
            "/api/v1/planner/decision",
            json={
                "recommendation_id": rec_id,
                "action": "APPROVED",
                "chosen_start": "2099-01-01T10:00:00",
                "chosen_end": "2099-01-01T11:00:00",
            },
        )
        assert response.status_code == 200
        body = response.json()
        # final_start must equal the stored recommended_start, not the invented slot
        rec = db_session.query(AIRecommendation).filter(AIRecommendation.id == rec_id).first()
        db_session.refresh(rec)
        assert rec.final_start == rec.recommended_start
        assert rec.final_end == rec.recommended_end

    def test_decision_modified_valid_slot(self, client, db_session, mock_provider):
        rec_body = self._make_recommendation(client, db_session)
        rec_id = rec_body["recommendation_id"]

        # Use the first candidate from the response (guaranteed to be in the stored list)
        first_candidate = rec_body["candidate_slots"][0]
        chosen_start = first_candidate["start_datetime"]
        chosen_end = first_candidate["end_datetime"]

        response = client.post(
            "/api/v1/planner/decision",
            json={
                "recommendation_id": rec_id,
                "action": "MODIFIED",
                "chosen_start": chosen_start,
                "chosen_end": chosen_end,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["action"] == "MODIFIED"
        assert body["final_start"] is not None
        assert body["final_end"] is not None

    def test_decision_rejected(self, client, db_session, mock_provider):
        rec_body = self._make_recommendation(client, db_session)
        rec_id = rec_body["recommendation_id"]

        response = client.post(
            "/api/v1/planner/decision",
            json={"recommendation_id": rec_id, "action": "REJECTED"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["action"] == "REJECTED"
        assert body["final_start"] is None
        assert body["final_end"] is None
        assert "pending" in body["message"]

    def test_decision_task_status_not_changed(self, client, db_session, mock_provider):
        """Decision endpoint must never alter Task.status."""
        task = _make_task(db_session)
        response = client.post(
            "/api/v1/planner/recommend", json={"task_id": task.id}
        )
        rec_id = response.json()["recommendation_id"]

        client.post(
            "/api/v1/planner/decision",
            json={"recommendation_id": rec_id, "action": "APPROVED"},
        )

        db_session.refresh(task)
        assert task.status == TaskStatus.pending

    def test_decision_not_found(self, client, db_session, mock_provider):
        response = client.post(
            "/api/v1/planner/decision",
            json={"recommendation_id": 99999, "action": "APPROVED"},
        )
        assert response.status_code == 404
        assert "recommendation not found" in response.json()["detail"]

    def test_decision_already_recorded(self, client, db_session, mock_provider):
        rec_body = self._make_recommendation(client, db_session)
        rec_id = rec_body["recommendation_id"]

        # First decision
        client.post(
            "/api/v1/planner/decision",
            json={"recommendation_id": rec_id, "action": "APPROVED"},
        )

        # Second decision on the same recommendation
        response = client.post(
            "/api/v1/planner/decision",
            json={"recommendation_id": rec_id, "action": "REJECTED"},
        )
        assert response.status_code == 409
        assert "already recorded" in response.json()["detail"]

    def test_decision_modified_slot_not_in_list(self, client, db_session, mock_provider):
        rec_body = self._make_recommendation(client, db_session)
        rec_id = rec_body["recommendation_id"]

        response = client.post(
            "/api/v1/planner/decision",
            json={
                "recommendation_id": rec_id,
                "action": "MODIFIED",
                "chosen_start": "2099-01-01T10:00:00",
                "chosen_end": "2099-01-01T11:00:00",
            },
        )
        assert response.status_code == 422
        assert "not in the original candidate list" in response.json()["detail"]

    def test_decision_modified_missing_chosen_start(self, client, db_session, mock_provider):
        rec_body = self._make_recommendation(client, db_session)
        rec_id = rec_body["recommendation_id"]

        response = client.post(
            "/api/v1/planner/decision",
            json={"recommendation_id": rec_id, "action": "MODIFIED"},
        )
        assert response.status_code == 422
        assert "chosen_start and chosen_end are required" in response.json()["detail"]

    def test_decision_rejected_ignores_chosen_slot(self, client, db_session, mock_provider):
        """REJECTED ignores any chosen_start/end — final_start/end remain null."""
        rec_body = self._make_recommendation(client, db_session)
        rec_id = rec_body["recommendation_id"]

        response = client.post(
            "/api/v1/planner/decision",
            json={
                "recommendation_id": rec_id,
                "action": "REJECTED",
                "chosen_start": "2099-01-01T10:00:00",
                "chosen_end": "2099-01-01T11:00:00",
            },
        )
        assert response.status_code == 200
        assert response.json()["final_start"] is None
        assert response.json()["final_end"] is None

    def test_recommend_does_not_change_task_status(self, client, db_session, mock_provider):
        """POST /planner/recommend must never mutate Task.status."""
        task = _make_task(db_session)
        client.post("/api/v1/planner/recommend", json={"task_id": task.id})
        db_session.refresh(task)
        assert task.status == TaskStatus.pending

    def test_multiple_recommendations_same_task(self, client, db_session, mock_provider):
        """Multiple recommendations for the same pending task are all valid; each has its own row."""
        task = _make_task(db_session)

        r1 = client.post("/api/v1/planner/recommend", json={"task_id": task.id})
        r2 = client.post("/api/v1/planner/recommend", json={"task_id": task.id})

        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.json()["recommendation_id"] != r2.json()["recommendation_id"]

        rows = (
            db_session.query(AIRecommendation)
            .filter(AIRecommendation.task_id == task.id)
            .all()
        )
        assert len(rows) == 2


# ---------------------------------------------------------------------------
# TestAuditMetadata — Gap 1: provider audit uses injected provider, not settings
# ---------------------------------------------------------------------------


class TestAuditMetadata:
    """Verify that AIRecommendation.provider / model_id reflect the injected provider
    instance, not settings.AI_PROVIDER.

    The critical case: settings.AI_PROVIDER could be 'watsonx' in the environment
    while the DI graph injects a MockProvider (as happens in every test run).
    The audit row must say 'mock', not 'watsonx'.
    """

    def test_audit_provider_is_mock_when_mock_injected(self, client, db_session):
        """Audit row must record 'mock' even if settings.AI_PROVIDER were 'watsonx'.

        We inject MockProvider explicitly (same as what tests always do) and confirm
        the persisted provider/model_id values come from the provider instance, not
        from settings.
        """
        from app.core.settings import settings as app_settings

        # Inject MockProvider regardless of what settings.AI_PROVIDER says.
        provider = MockProvider(fixed_response=_VALID_MOCK_RESPONSE)
        app.dependency_overrides[get_provider] = lambda: provider
        try:
            task = _make_task(db_session)
            response = client.post(
                "/api/v1/planner/recommend", json={"task_id": task.id}
            )
            assert response.status_code == 201
            rec_id = response.json()["recommendation_id"]

            rec = db_session.query(AIRecommendation).filter(
                AIRecommendation.id == rec_id
            ).first()

            # Audit must reflect the injected MockProvider — always "mock".
            assert rec.provider == "mock", (
                f"Expected 'mock' but got {rec.provider!r}. "
                "persist_recommendation must use the injected provider, not settings."
            )
            assert rec.model_id == "mock", (
                f"Expected 'mock' but got {rec.model_id!r}."
            )
        finally:
            del app.dependency_overrides[get_provider]

    def test_audit_provider_does_not_use_settings_ai_provider(self, client, db_session):
        """When DI injects MockProvider and settings.AI_PROVIDER disagrees, audit wins.

        Simulate the exact divergence scenario: temporarily shadow settings.AI_PROVIDER
        to 'watsonx' while injecting MockProvider via DI.  The audit row must still
        record 'mock' because it reads from the provider instance, not settings.
        """
        from app.core import settings as settings_module

        original = settings_module.settings.AI_PROVIDER

        # Temporarily override the settings value to simulate a watsonx deployment.
        settings_module.settings.AI_PROVIDER = "watsonx"
        provider = MockProvider(fixed_response=_VALID_MOCK_RESPONSE)
        app.dependency_overrides[get_provider] = lambda: provider
        try:
            task = _make_task(db_session)
            response = client.post(
                "/api/v1/planner/recommend", json={"task_id": task.id}
            )
            assert response.status_code == 201
            rec_id = response.json()["recommendation_id"]

            rec = db_session.query(AIRecommendation).filter(
                AIRecommendation.id == rec_id
            ).first()

            # Despite settings saying "watsonx", the injected MockProvider governs.
            assert rec.provider == "mock"
            assert rec.model_id == "mock"
        finally:
            settings_module.settings.AI_PROVIDER = original
            del app.dependency_overrides[get_provider]


# ---------------------------------------------------------------------------
# TestFromDateValidation — Gap 2: from_date past validation in planner router
# ---------------------------------------------------------------------------


class TestFromDateValidation:
    """Verify from_date validation in POST /api/v1/planner/recommend."""

    def test_recommend_from_date_in_past(self, client, db_session, mock_provider):
        """from_date in the past must return 422."""
        from datetime import timedelta
        task = _make_task(db_session)
        past_date = (clock.now().date() - timedelta(days=1)).isoformat()

        response = client.post(
            "/api/v1/planner/recommend",
            json={"task_id": task.id, "from_date": past_date},
        )
        assert response.status_code == 422
        assert "from_date cannot be in the past" in response.json()["detail"]

    def test_recommend_from_date_today_accepted(self, client, db_session, mock_provider):
        """from_date == today must be accepted (boundary: today is valid)."""
        task = _make_task(db_session)
        today = clock.now().date().isoformat()

        response = client.post(
            "/api/v1/planner/recommend",
            json={"task_id": task.id, "from_date": today},
        )
        assert response.status_code == 201


@pytest.mark.parametrize("fixed_response", [_VALID_MOCK_RESPONSE, _INVALID_MOCK_RESPONSE])
def test_planner_cutoff_reaches_agent(client, db_session, monkeypatch, mock_provider,
                                     fixed_response):
    import app.routers.planner as router_module
    from unittest.mock import Mock
    captured = datetime(2026, 10, 7, 15, 30)
    task = _make_task(db_session)
    clock_spy = Mock(return_value=captured)
    monkeypatch.setattr(clock, "now", clock_spy)
    service_spy = Mock(wraps=router_module.suggest_slots)
    monkeypatch.setattr(router_module, "suggest_slots", service_spy)
    recommend_spy = Mock(wraps=router_module.PlannerAgent.recommend)
    monkeypatch.setattr(router_module.PlannerAgent, "recommend",
                        lambda self, inp: recommend_spy(self, inp))
    monkeypatch.setattr(mock_provider, "_response", fixed_response)
    response = client.post("/api/v1/planner/recommend", json={"task_id": task.id})
    assert response.status_code == 201
    clock_spy.assert_called_once_with()
    assert service_spy.call_args.kwargs["now"] is captured
    assert service_spy.call_args.kwargs["from_date"] == captured.date()
    agent_input = recommend_spy.call_args.args[1]
    assert all(s.start_datetime > captured for s in agent_input.candidate_slots)
    assert datetime.fromisoformat(response.json()["recommended_slot"]["start_datetime"]) > captured
    assert response.json()["fallback_used"] == (fixed_response == _INVALID_MOCK_RESPONSE)


def test_planner_no_remaining_candidates_no_provider_or_audit(
        client, db_session, monkeypatch, mock_provider):
    from unittest.mock import Mock
    captured = datetime(2026, 10, 7, 21, 30)
    task = _make_task(db_session, duration_minutes=60, deadline=captured.date())
    monkeypatch.setattr(clock, "now", lambda: captured)
    complete_spy = Mock(wraps=mock_provider.complete)
    monkeypatch.setattr(mock_provider, "complete", complete_spy)
    response = client.post("/api/v1/planner/recommend", json={"task_id": task.id})
    assert response.status_code == 422
    complete_spy.assert_not_called()
    assert db_session.query(AIRecommendation).count() == 0
    db_session.refresh(task)
    assert task.status == TaskStatus.pending
