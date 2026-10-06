"""
Unit tests for PlannerAgent and the get_provider configuration guard.

All tests use MockProvider — no database, no real AI provider, no network calls.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from unittest.mock import patch

import pytest

from app.ai.agent import PlannerAgent
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


def _valid_response(candidate_id: int = 1, reason_codes: list[str] | None = None) -> str:
    if reason_codes is None:
        reason_codes = ["DEADLINE_CLOSE", "HIGH_PRIORITY"]
    return json.dumps(
        {
            "recommended_candidate_id": candidate_id,
            "reason_codes": reason_codes,
            "explanation": "This slot is recommended because the deadline is close.",
        }
    )


# ---------------------------------------------------------------------------
# Test 1 — Happy path
# ---------------------------------------------------------------------------

def test_recommend_valid_response() -> None:
    """
    Model returns candidate_id=1.
    Agent returns the slot at index 1 from the candidate list, fallback_used=False.
    """
    candidates = _two_slots()
    provider = MockProvider(fixed_response=_valid_response(candidate_id=1))
    agent = PlannerAgent(provider)

    result = agent.recommend(AgentInput(task=_task(), candidate_slots=candidates))

    assert isinstance(result, PlannerRecommendation)
    assert result.fallback_used is False
    assert result.recommended_slot.start_datetime == candidates[1].start_datetime
    assert result.recommended_slot.end_datetime == candidates[1].end_datetime
    assert ReasonCode.DEADLINE_CLOSE in result.reason_codes
    assert ReasonCode.HIGH_PRIORITY in result.reason_codes
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
    bad_response = json.dumps({"reason_codes": ["EARLIEST_SLOT"], "explanation": "ok"})
    provider = MockProvider(fixed_response=bad_response)
    agent = PlannerAgent(provider)

    result = agent.recommend(AgentInput(task=_task(), candidate_slots=candidates))

    assert result.fallback_used is True
    assert ReasonCode.PROVIDER_FALLBACK in result.reason_codes


# ---------------------------------------------------------------------------
# Test 5 — Unknown reason code triggers fallback
# ---------------------------------------------------------------------------

def test_recommend_fallback_unknown_reason_code() -> None:
    """Model returns an unrecognised reason code string → fallback."""
    candidates = _two_slots()
    bad_response = json.dumps(
        {
            "recommended_candidate_id": 0,
            "reason_codes": ["MADE_UP_CODE"],
            "explanation": "ok",
        }
    )
    provider = MockProvider(fixed_response=bad_response)
    agent = PlannerAgent(provider)

    result = agent.recommend(AgentInput(task=_task(), candidate_slots=candidates))

    assert result.fallback_used is True
    assert ReasonCode.PROVIDER_FALLBACK in result.reason_codes


# ---------------------------------------------------------------------------
# Test 6 — Model self-declares PROVIDER_FALLBACK → fallback
# ---------------------------------------------------------------------------

def test_recommend_fallback_provider_fallback_in_output() -> None:
    """
    Model returns PROVIDER_FALLBACK in reason_codes.
    That code is reserved for system use — agent must reject it and fall back.
    """
    candidates = _two_slots()
    bad_response = json.dumps(
        {
            "recommended_candidate_id": 0,
            "reason_codes": ["PROVIDER_FALLBACK"],
            "explanation": "ok",
        }
    )
    provider = MockProvider(fixed_response=bad_response)
    agent = PlannerAgent(provider)

    result = agent.recommend(AgentInput(task=_task(), candidate_slots=candidates))

    assert result.fallback_used is True
    assert ReasonCode.PROVIDER_FALLBACK in result.reason_codes


# ---------------------------------------------------------------------------
# Test 7 — candidate_id out of range (positive) → fallback
# ---------------------------------------------------------------------------

def test_recommend_fallback_candidate_id_out_of_range() -> None:
    """Model returns candidate_id=99 for a 2-item list → out of range → fallback."""
    candidates = _two_slots()
    bad_response = json.dumps(
        {
            "recommended_candidate_id": 99,
            "reason_codes": ["EARLIEST_SLOT"],
            "explanation": "ok",
        }
    )
    provider = MockProvider(fixed_response=bad_response)
    agent = PlannerAgent(provider)

    result = agent.recommend(AgentInput(task=_task(), candidate_slots=candidates))

    assert result.fallback_used is True
    assert result.recommended_slot.start_datetime == candidates[0].start_datetime


# ---------------------------------------------------------------------------
# Test 8 — candidate_id negative → fallback
# ---------------------------------------------------------------------------

def test_recommend_fallback_candidate_id_negative() -> None:
    """Model returns candidate_id=-1 → negative index rejected → fallback."""
    candidates = _two_slots()
    bad_response = json.dumps(
        {
            "recommended_candidate_id": -1,
            "reason_codes": ["EARLIEST_SLOT"],
            "explanation": "ok",
        }
    )
    provider = MockProvider(fixed_response=bad_response)
    agent = PlannerAgent(provider)

    result = agent.recommend(AgentInput(task=_task(), candidate_slots=candidates))

    assert result.fallback_used is True
    assert result.recommended_slot.start_datetime == candidates[0].start_datetime


# ---------------------------------------------------------------------------
# Test 9 — Empty candidate list raises ValueError
# ---------------------------------------------------------------------------

def test_recommend_raises_on_empty_candidates() -> None:
    """candidate_slots=[] → ValueError raised before calling the provider."""
    provider = MockProvider(fixed_response="{}")
    agent = PlannerAgent(provider)

    with pytest.raises(ValueError, match="No candidate slots provided"):
        agent.recommend(AgentInput(task=_task(), candidate_slots=[]))


# ---------------------------------------------------------------------------
# Test 10 — Explanation longer than 200 chars is truncated (not a fallback)
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
            "reason_codes": ["EARLIEST_SLOT"],
            "explanation": long_explanation,
        }
    )
    provider = MockProvider(fixed_response=response)
    agent = PlannerAgent(provider)

    result = agent.recommend(AgentInput(task=_task(), candidate_slots=candidates))

    assert result.fallback_used is False
    assert len(result.explanation) == 200


# ---------------------------------------------------------------------------
# Test 11 — Single candidate → valid recommendation
# ---------------------------------------------------------------------------

def test_recommend_only_slot_available() -> None:
    """Single candidate in list → model returns candidate_id=0 → valid recommendation."""
    candidates = [_slot(5, 10)]
    response = json.dumps(
        {
            "recommended_candidate_id": 0,
            "reason_codes": ["ONLY_SLOT_AVAILABLE"],
            "explanation": "Only one slot is available.",
        }
    )
    provider = MockProvider(fixed_response=response)
    agent = PlannerAgent(provider)

    result = agent.recommend(AgentInput(task=_task(), candidate_slots=candidates))

    assert result.fallback_used is False
    assert result.recommended_slot.start_datetime == candidates[0].start_datetime
    assert ReasonCode.ONLY_SLOT_AVAILABLE in result.reason_codes


# ---------------------------------------------------------------------------
# Test 12 — Markdown code fences stripped before JSON parsing
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
            "reason_codes": ["EARLIEST_SLOT"],
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
# Test 13 — get_provider: mock and invalid values
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
