"""
Unit tests for PlannerAgent, _derive_codes, and the get_provider configuration guard.

All tests use MockProvider — no database, no real AI provider, no network calls.

Key change from previous version:
- The model no longer supplies reason_codes.  Model responses contain only
  recommended_candidate_id and explanation.
- reason_codes are derived deterministically by _derive_codes() after candidate
  validation.  Tests that previously checked fallback on unknown/reserved codes
  are removed because those paths no longer exist.
- New TestDeriveCodes group tests _derive_codes directly.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from unittest.mock import patch

import pytest

from app.ai.agent import PlannerAgent, _derive_codes
from app.ai.provider import ConfigurationError, MockProvider, ProviderError
from app.ai.schemas import (
    AgentInput,
    CandidateSlot,
    PlannerRecommendation,
    ReasonCode,
    TaskSummary,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _task(
    priority: str = "high",
    deadline: date | None = date(2026, 10, 10),
) -> TaskSummary:
    return TaskSummary(
        id=1,
        title="Study for exam",
        duration_minutes=90,
        priority=priority,
        deadline=deadline,
        status="pending",
    )


def _slot(day: int, start_hour: int) -> CandidateSlot:
    start = datetime(2026, 10, day, start_hour, 0)
    end = datetime(2026, 10, day, start_hour + 2, 0)
    return CandidateSlot(
        start_datetime=start,
        end_datetime=end,
        date=date(2026, 10, day),
    )


def _two_slots() -> list[CandidateSlot]:
    return [_slot(5, 8), _slot(5, 14)]


def _valid_response(candidate_id: int = 1) -> str:
    """Model response: candidate_id + explanation only.  No reason_codes."""
    return json.dumps(
        {
            "recommended_candidate_id": candidate_id,
            "explanation": "This slot fits well given the task requirements.",
        }
    )


# ---------------------------------------------------------------------------
# Test 1 — Happy path
# ---------------------------------------------------------------------------

def test_recommend_valid_response() -> None:
    """
    Model returns candidate_id=1.
    Agent returns the slot at index 1 from the candidate list, fallback_used=False.
    reason_codes are derived deterministically:
      - priority="high" -> HIGH_PRIORITY
      - cid=1 -> EARLIEST_SLOT does NOT fire (cid != 0)
      - 2 candidates -> ONLY_SLOT_AVAILABLE does NOT fire
      - deadline=2026-10-10, slot date=2026-10-05 -> delta=5 days -> DEADLINE_CLOSE does NOT fire
    Expected codes: [HIGH_PRIORITY]
    """
    candidates = _two_slots()
    provider = MockProvider(fixed_response=_valid_response(candidate_id=1))
    agent = PlannerAgent(provider)

    result = agent.recommend(AgentInput(task=_task(), candidate_slots=candidates))

    assert isinstance(result, PlannerRecommendation)
    assert result.fallback_used is False
    assert result.recommended_slot.start_datetime == candidates[1].start_datetime
    assert result.recommended_slot.end_datetime == candidates[1].end_datetime
    assert result.reason_codes == [ReasonCode.HIGH_PRIORITY]
    assert len(result.explanation) <= 200


# ---------------------------------------------------------------------------
# Test 2 — ProviderError triggers fallback
# ---------------------------------------------------------------------------

class _ErrorProvider(MockProvider):
    """MockProvider subclass that always raises ProviderError."""

    def __init__(self) -> None:
        super().__init__(fixed_response="")

    def complete(self, prompt: str) -> str:  # noqa: ARG002
        raise ProviderError("simulated network failure")


def test_recommend_fallback_provider_error() -> None:
    """ProviderError from provider → fallback to candidates[0], fallback_used=True."""
    candidates = _two_slots()
    agent = PlannerAgent(_ErrorProvider())

    result = agent.recommend(AgentInput(task=_task(), candidate_slots=candidates))

    assert result.fallback_used is True
    assert result.recommended_slot.start_datetime == candidates[0].start_datetime
    assert result.recommended_slot.end_datetime == candidates[0].end_datetime
    assert ReasonCode.PROVIDER_FALLBACK in result.reason_codes


# ---------------------------------------------------------------------------
# Test 3 — Invalid JSON triggers fallback
# ---------------------------------------------------------------------------

def test_recommend_fallback_invalid_json() -> None:
    """Provider returns a non-JSON string → fallback."""
    candidates = _two_slots()
    provider = MockProvider(fixed_response="not valid json at all")
    agent = PlannerAgent(provider)

    result = agent.recommend(AgentInput(task=_task(), candidate_slots=candidates))

    assert result.fallback_used is True
    assert ReasonCode.PROVIDER_FALLBACK in result.reason_codes
    assert result.recommended_slot.start_datetime == candidates[0].start_datetime


# ---------------------------------------------------------------------------
# Test 4 — Missing required field triggers fallback
# ---------------------------------------------------------------------------

def test_recommend_fallback_pydantic_error() -> None:
    """
    Provider returns valid JSON but without recommended_candidate_id.
    Pydantic ValidationError → fallback.
    """
    candidates = _two_slots()
    bad_response = json.dumps({"explanation": "ok"})
    provider = MockProvider(fixed_response=bad_response)
    agent = PlannerAgent(provider)

    result = agent.recommend(AgentInput(task=_task(), candidate_slots=candidates))

    assert result.fallback_used is True
    assert ReasonCode.PROVIDER_FALLBACK in result.reason_codes


# ---------------------------------------------------------------------------
# Test 5 — candidate_id out of range (positive) → fallback
# ---------------------------------------------------------------------------

def test_recommend_fallback_candidate_id_out_of_range() -> None:
    """Model returns candidate_id=99 for a 2-item list → out of range → fallback."""
    candidates = _two_slots()
    bad_response = json.dumps(
        {
            "recommended_candidate_id": 99,
            "explanation": "ok",
        }
    )
    provider = MockProvider(fixed_response=bad_response)
    agent = PlannerAgent(provider)

    result = agent.recommend(AgentInput(task=_task(), candidate_slots=candidates))

    assert result.fallback_used is True
    assert result.recommended_slot.start_datetime == candidates[0].start_datetime


# ---------------------------------------------------------------------------
# Test 6 — candidate_id negative → fallback
# ---------------------------------------------------------------------------

def test_recommend_fallback_candidate_id_negative() -> None:
    """Model returns candidate_id=-1 → negative index rejected → fallback."""
    candidates = _two_slots()
    bad_response = json.dumps(
        {
            "recommended_candidate_id": -1,
            "explanation": "ok",
        }
    )
    provider = MockProvider(fixed_response=bad_response)
    agent = PlannerAgent(provider)

    result = agent.recommend(AgentInput(task=_task(), candidate_slots=candidates))

    assert result.fallback_used is True
    assert result.recommended_slot.start_datetime == candidates[0].start_datetime


# ---------------------------------------------------------------------------
# Test 7 — Empty candidate list raises ValueError
# ---------------------------------------------------------------------------

def test_recommend_raises_on_empty_candidates() -> None:
    """candidate_slots=[] → ValueError raised before calling the provider."""
    provider = MockProvider(fixed_response="{}")
    agent = PlannerAgent(provider)

    with pytest.raises(ValueError, match="No candidate slots provided"):
        agent.recommend(AgentInput(task=_task(), candidate_slots=[]))


# ---------------------------------------------------------------------------
# Test 8 — Explanation longer than 200 chars is truncated (not a fallback)
# ---------------------------------------------------------------------------

def test_recommend_explanation_truncated() -> None:
    """
    Model returns explanation > 200 chars.
    Agent truncates to 200 chars but still returns a valid recommendation
    (fallback_used=False).
    """
    long_explanation = "x" * 300
    candidates = _two_slots()
    response = json.dumps(
        {
            "recommended_candidate_id": 0,
            "explanation": long_explanation,
        }
    )
    provider = MockProvider(fixed_response=response)
    agent = PlannerAgent(provider)

    result = agent.recommend(AgentInput(task=_task(), candidate_slots=candidates))

    assert result.fallback_used is False
    assert len(result.explanation) == 200


# ---------------------------------------------------------------------------
# Test 9 — Single candidate → valid recommendation
# ---------------------------------------------------------------------------

def test_recommend_only_slot_available() -> None:
    """Single candidate in list → model returns candidate_id=0 → valid recommendation.
    Derived codes: HIGH_PRIORITY (priority=high), EARLIEST_SLOT (cid=0),
    ONLY_SLOT_AVAILABLE (1 candidate).
    DEADLINE_CLOSE: deadline=2026-10-10, slot date=2026-10-05 → delta=5 days → does NOT fire.
    """
    candidates = [_slot(5, 10)]
    response = json.dumps(
        {
            "recommended_candidate_id": 0,
            "explanation": "Only one slot is available.",
        }
    )
    provider = MockProvider(fixed_response=response)
    agent = PlannerAgent(provider)

    result = agent.recommend(AgentInput(task=_task(), candidate_slots=candidates))

    assert result.fallback_used is False
    assert result.recommended_slot.start_datetime == candidates[0].start_datetime
    assert ReasonCode.ONLY_SLOT_AVAILABLE in result.reason_codes
    assert ReasonCode.EARLIEST_SLOT in result.reason_codes
    assert ReasonCode.HIGH_PRIORITY in result.reason_codes


# ---------------------------------------------------------------------------
# Test 10 — Markdown code fences stripped before JSON parsing
# ---------------------------------------------------------------------------

def test_recommend_json_with_code_fences() -> None:
    """
    Provider wraps the JSON in markdown code fences (```json ... ```).
    Agent strips fences before parsing — no fallback triggered.
    """
    candidates = _two_slots()
    inner = json.dumps(
        {
            "recommended_candidate_id": 0,
            "explanation": "Earliest slot.",
        }
    )
    fenced_response = f"```json\n{inner}\n```"
    provider = MockProvider(fixed_response=fenced_response)
    agent = PlannerAgent(provider)

    result = agent.recommend(AgentInput(task=_task(), candidate_slots=candidates))

    assert result.fallback_used is False
    assert result.recommended_slot.start_datetime == candidates[0].start_datetime


# ---------------------------------------------------------------------------
# Test 11 — Model includes extra fields (e.g. old reason_codes) — silently ignored
# ---------------------------------------------------------------------------

def test_recommend_extra_model_fields_ignored() -> None:
    """
    Model includes reason_codes in output (old contract).
    Pydantic silently ignores the extra field; candidate_id and explanation are used.
    No fallback triggered.
    """
    candidates = _two_slots()
    response = json.dumps(
        {
            "recommended_candidate_id": 1,
            "reason_codes": ["EARLIEST_SLOT", "PROVIDER_FALLBACK", "MADE_UP_CODE"],
            "explanation": "First slot.",
        }
    )
    provider = MockProvider(fixed_response=response)
    agent = PlannerAgent(provider)

    result = agent.recommend(AgentInput(task=_task(), candidate_slots=candidates))

    # Should succeed — extra field ignored, fallback_used=False
    assert result.fallback_used is False
    assert result.recommended_slot.start_datetime == candidates[1].start_datetime
    # Conflicting, reserved and unknown model codes cannot influence the result.
    assert result.reason_codes == [ReasonCode.HIGH_PRIORITY]


# ---------------------------------------------------------------------------
# Test 12 — get_provider: mock and invalid values
# ---------------------------------------------------------------------------

def test_get_provider_mock() -> None:
    """AI_PROVIDER='mock' → get_provider returns a MockProvider instance."""
    from app.ai.provider import get_provider

    with patch("app.ai.provider.settings") as mock_settings:
        mock_settings.AI_PROVIDER = "mock"
        provider = get_provider()

    assert isinstance(provider, MockProvider)


def test_get_provider_invalid() -> None:
    """AI_PROVIDER='openai' → get_provider raises ConfigurationError."""
    from app.ai.provider import get_provider

    with patch("app.ai.provider.settings") as mock_settings:
        mock_settings.AI_PROVIDER = "openai"
        with pytest.raises(ConfigurationError, match="Unknown AI_PROVIDER value"):
            get_provider()


# ---------------------------------------------------------------------------
# TestDeriveCodes — direct unit tests for _derive_codes()
# ---------------------------------------------------------------------------

class TestDeriveCodes:
    """Direct unit tests for the _derive_codes pure function."""

    def _make_slot(self, day: int) -> CandidateSlot:
        start = datetime(2026, 10, day, 8, 0)
        end = datetime(2026, 10, day, 9, 0)
        return CandidateSlot(start_datetime=start, end_datetime=end, date=date(2026, 10, day))

    def _make_task(
        self,
        priority: str = "high",
        deadline: date | None = None,
    ) -> TaskSummary:
        return TaskSummary(
            id=1,
            title="Test",
            duration_minutes=60,
            priority=priority,
            deadline=deadline,
            status="pending",
        )

    def test_high_priority_fires(self) -> None:
        """HIGH_PRIORITY fires for priority='high'."""
        candidates = [self._make_slot(5), self._make_slot(6)]
        task = self._make_task(priority="high")
        codes = _derive_codes(1, candidates, task)
        assert ReasonCode.HIGH_PRIORITY in codes
        assert ReasonCode.MEDIUM_PRIORITY not in codes
        assert ReasonCode.LOW_PRIORITY not in codes

    def test_medium_priority_fires(self) -> None:
        """MEDIUM_PRIORITY fires for priority='medium'."""
        candidates = [self._make_slot(5), self._make_slot(6)]
        task = self._make_task(priority="medium")
        codes = _derive_codes(1, candidates, task)
        assert ReasonCode.MEDIUM_PRIORITY in codes
        assert ReasonCode.HIGH_PRIORITY not in codes
        assert ReasonCode.LOW_PRIORITY not in codes

    def test_low_priority_fires(self) -> None:
        """LOW_PRIORITY fires for priority='low'."""
        candidates = [self._make_slot(5), self._make_slot(6)]
        task = self._make_task(priority="low")
        codes = _derive_codes(1, candidates, task)
        assert ReasonCode.LOW_PRIORITY in codes
        assert ReasonCode.HIGH_PRIORITY not in codes
        assert ReasonCode.MEDIUM_PRIORITY not in codes

    def test_exactly_one_priority_code_always_fires(self) -> None:
        """Exactly one priority code fires regardless of other attributes."""
        candidates = [self._make_slot(5)]
        for priority in ("high", "medium", "low"):
            task = self._make_task(priority=priority)
            codes = _derive_codes(0, candidates, task)
            priority_codes = [c for c in codes if c in (
                ReasonCode.HIGH_PRIORITY, ReasonCode.MEDIUM_PRIORITY, ReasonCode.LOW_PRIORITY
            )]
            assert len(priority_codes) == 1

    def test_earliest_slot_fires_for_cid_zero(self) -> None:
        """EARLIEST_SLOT fires when cid == 0."""
        candidates = [self._make_slot(5), self._make_slot(6)]
        task = self._make_task(priority="high")
        codes = _derive_codes(0, candidates, task)
        assert ReasonCode.EARLIEST_SLOT in codes

    def test_earliest_slot_does_not_fire_for_cid_nonzero(self) -> None:
        """EARLIEST_SLOT does not fire when cid != 0."""
        candidates = [self._make_slot(5), self._make_slot(6)]
        task = self._make_task(priority="high")
        codes = _derive_codes(1, candidates, task)
        assert ReasonCode.EARLIEST_SLOT not in codes

    def test_only_slot_available_fires_for_single_candidate(self) -> None:
        """ONLY_SLOT_AVAILABLE fires when there is exactly one candidate."""
        candidates = [self._make_slot(5)]
        task = self._make_task(priority="medium")
        codes = _derive_codes(0, candidates, task)
        assert ReasonCode.ONLY_SLOT_AVAILABLE in codes

    def test_only_slot_available_does_not_fire_for_multiple_candidates(self) -> None:
        """ONLY_SLOT_AVAILABLE does not fire when len(candidates) > 1."""
        candidates = [self._make_slot(5), self._make_slot(6)]
        task = self._make_task(priority="medium")
        codes = _derive_codes(0, candidates, task)
        assert ReasonCode.ONLY_SLOT_AVAILABLE not in codes

    def test_deadline_close_fires_same_day(self) -> None:
        """DEADLINE_CLOSE fires when the slot date == the deadline date (delta=0 days)."""
        slot_day = date(2026, 10, 5)
        slot = CandidateSlot(
            start_datetime=datetime(2026, 10, 5, 8, 0),
            end_datetime=datetime(2026, 10, 5, 9, 0),
            date=slot_day,
        )
        task = self._make_task(priority="high", deadline=date(2026, 10, 5))
        codes = _derive_codes(0, [slot], task)
        assert ReasonCode.DEADLINE_CLOSE in codes

    def test_deadline_close_fires_one_day_before(self) -> None:
        """DEADLINE_CLOSE fires when the slot is the day before the deadline (delta=1 day)."""
        slot = CandidateSlot(
            start_datetime=datetime(2026, 10, 5, 8, 0),
            end_datetime=datetime(2026, 10, 5, 9, 0),
            date=date(2026, 10, 5),
        )
        task = self._make_task(priority="high", deadline=date(2026, 10, 6))
        codes = _derive_codes(0, [slot], task)
        assert ReasonCode.DEADLINE_CLOSE in codes

    def test_deadline_close_does_not_fire_two_days_before(self) -> None:
        """DEADLINE_CLOSE does not fire when delta == 2 days."""
        slot = CandidateSlot(
            start_datetime=datetime(2026, 10, 5, 8, 0),
            end_datetime=datetime(2026, 10, 5, 9, 0),
            date=date(2026, 10, 5),
        )
        task = self._make_task(priority="high", deadline=date(2026, 10, 7))
        codes = _derive_codes(0, [slot], task)
        assert ReasonCode.DEADLINE_CLOSE not in codes

    def test_deadline_close_does_not_fire_without_deadline(self) -> None:
        """DEADLINE_CLOSE does not fire when task has no deadline."""
        candidates = [self._make_slot(5)]
        task = self._make_task(priority="high", deadline=None)
        codes = _derive_codes(0, candidates, task)
        assert ReasonCode.DEADLINE_CLOSE not in codes

    def test_all_codes_can_fire_simultaneously(self) -> None:
        """HIGH_PRIORITY + EARLIEST_SLOT + ONLY_SLOT_AVAILABLE + DEADLINE_CLOSE all fire."""
        slot = CandidateSlot(
            start_datetime=datetime(2026, 10, 5, 8, 0),
            end_datetime=datetime(2026, 10, 5, 9, 0),
            date=date(2026, 10, 5),
        )
        # cid=0, 1 candidate, priority=high, deadline same day
        task = self._make_task(priority="high", deadline=date(2026, 10, 5))
        codes = _derive_codes(0, [slot], task)
        assert ReasonCode.HIGH_PRIORITY in codes
        assert ReasonCode.EARLIEST_SLOT in codes
        assert ReasonCode.ONLY_SLOT_AVAILABLE in codes
        assert ReasonCode.DEADLINE_CLOSE in codes

    def test_low_priority_no_deadline_non_earliest(self) -> None:
        """Low priority, no deadline, cid=1, 2 candidates → only LOW_PRIORITY fires."""
        candidates = [self._make_slot(5), self._make_slot(6)]
        task = self._make_task(priority="low", deadline=None)
        codes = _derive_codes(1, candidates, task)
        assert codes == [ReasonCode.LOW_PRIORITY]

    def test_provider_fallback_never_derived(self) -> None:
        """PROVIDER_FALLBACK must never appear in deterministically derived codes."""
        for priority in ("high", "medium", "low"):
            for cid in (0, 1):
                candidates = [self._make_slot(5), self._make_slot(6)]
                task = self._make_task(priority=priority)
                codes = _derive_codes(cid, candidates, task)
                assert ReasonCode.PROVIDER_FALLBACK not in codes

@pytest.mark.parametrize("payload", [
    {"recommended_candidate_id": 0},
    {"recommended_candidate_id": None, "explanation": "ok"},
    {"recommended_candidate_id": True, "explanation": "ok"},
    {"recommended_candidate_id": "0", "explanation": "ok"},
    {"recommended_candidate_id": 0.0, "explanation": "ok"},
    {"recommended_candidate_id": 0.5, "explanation": "ok"},
    {"recommended_candidate_id": 0, "explanation": None},
    {"recommended_candidate_id": 0, "explanation": 7},
    [],
    None,
])
def test_invalid_structural_response_falls_back(payload) -> None:
    candidates = _two_slots()
    agent = PlannerAgent(MockProvider(json.dumps(payload)))
    result = agent.recommend(AgentInput(task=_task(), candidate_slots=candidates))
    assert result.fallback_used is True
    assert result.reason_codes == [ReasonCode.PROVIDER_FALLBACK]
    assert result.recommended_slot.start_datetime == candidates[0].start_datetime


@pytest.mark.parametrize("priority,expected", [
    ("high", ReasonCode.HIGH_PRIORITY),
    ("medium", ReasonCode.MEDIUM_PRIORITY),
    ("low", ReasonCode.LOW_PRIORITY),
])
def test_recommend_derives_combined_codes_from_selected_candidate(priority, expected) -> None:
    candidates = [_slot(5, 8), _slot(6, 14)]
    agent = PlannerAgent(MockProvider(_valid_response(1)))
    result = agent.recommend(AgentInput(
        task=_task(priority=priority, deadline=date(2026, 10, 7)),
        candidate_slots=candidates,
    ))
    assert result.fallback_used is False
    # Date subtraction must use the selected candidate, not candidates[0].
    assert result.reason_codes == [expected, ReasonCode.DEADLINE_CLOSE]


def test_unrecognized_priority_is_not_labeled_low() -> None:
    assert _derive_codes(1, _two_slots(), _task(priority="unexpected", deadline=None)) == []


def test_prompt_only_requests_candidate_and_explanation() -> None:
    agent = PlannerAgent(MockProvider("{}"))
    prompt = agent._build_prompt(AgentInput(task=_task(), candidate_slots=_two_slots()))
    assert '"recommended_candidate_id"' in prompt
    assert '"explanation"' in prompt
    assert "reason_codes" not in prompt
    assert "MOST_BUFFER_BEFORE_DEADLINE" not in prompt


def test_reason_code_vocabulary_matches_approved_design() -> None:
    assert {code.value for code in ReasonCode} == {
        "HIGH_PRIORITY", "MEDIUM_PRIORITY", "LOW_PRIORITY", "EARLIEST_SLOT",
        "ONLY_SLOT_AVAILABLE", "DEADLINE_CLOSE", "PROVIDER_FALLBACK",
    }
