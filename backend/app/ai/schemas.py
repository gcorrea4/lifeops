"""
AI layer Pydantic schemas.

These types define the contract between the deterministic engine output, the
Planner Agent, and the recommendation response returned to the client.

No chain-of-thought or hidden reasoning is modelled here — only the structured
fields that are auditable and explainable.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Reason codes
# ---------------------------------------------------------------------------

class ReasonCode(str, Enum):
    """
    Vocabulary of explanatory codes attached to a recommendation.

    All codes except PROVIDER_FALLBACK are derived deterministically by the
    backend after the model selects a valid candidate_id.  The model never
    supplies reason codes; it supplies only a candidate_id and an explanation.
    """

    DEADLINE_CLOSE = "DEADLINE_CLOSE"
    """Applied when the selected slot falls on the deadline date or the
    calendar day immediately before it:
    (deadline - selected_candidate.date).days <= 1."""

    HIGH_PRIORITY = "HIGH_PRIORITY"
    """Applied when task.priority == 'high'."""

    MEDIUM_PRIORITY = "MEDIUM_PRIORITY"
    """Applied when task.priority == 'medium'."""

    LOW_PRIORITY = "LOW_PRIORITY"
    """Applied when task.priority == 'low'."""

    EARLIEST_SLOT = "EARLIEST_SLOT"
    """Applied when the selected candidate_id == 0 (engine returns candidates
    in ascending start order, so index 0 is definitionally the earliest)."""

    ONLY_SLOT_AVAILABLE = "ONLY_SLOT_AVAILABLE"
    """Applied when only one candidate slot was provided by the deterministic
    engine (len(candidates) == 1)."""

    PROVIDER_FALLBACK = "PROVIDER_FALLBACK"
    """System-only.  Applied when the AI provider failed or returned an invalid
    response; the first valid candidate is selected deterministically."""


# ---------------------------------------------------------------------------
# Agent input
# ---------------------------------------------------------------------------

class TaskSummary(BaseModel):
    """Minimal task fields passed to the Planner Agent prompt."""

    id: int
    title: str
    duration_minutes: int
    priority: str
    deadline: Optional[date] = None
    status: str


class CandidateSlot(BaseModel):
    """A single deterministically-validated candidate slot."""

    start_datetime: datetime
    end_datetime: datetime
    date: date


class AgentInput(BaseModel):
    """
    Full input delivered to the Planner Agent.

    candidate_slots contains at most 10 entries — the direct output of
    GET /engine/suggest, already validated by the deterministic engine.
    """

    task: TaskSummary
    candidate_slots: list[CandidateSlot]


# ---------------------------------------------------------------------------
# Agent output (structured recommendation)
# ---------------------------------------------------------------------------

class RecommendedSlot(BaseModel):
    """The single slot the agent chose from the candidate list."""

    start_datetime: datetime
    end_datetime: datetime


class PlannerRecommendation(BaseModel):
    """
    Structured output produced by PlannerAgent.recommend().

    Chain-of-thought is never stored here.
    Only the decision, codes, and a short explanation are retained.
    """

    recommended_slot: RecommendedSlot
    reason_codes: list[ReasonCode]
    explanation: str = Field(max_length=200)
    fallback_used: bool = False
