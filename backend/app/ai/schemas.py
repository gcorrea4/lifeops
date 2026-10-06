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
    Vocabulary of explanatory codes the Planner Agent may attach to a
    recommendation.  New codes must be added here before the agent can use them.
    """

    DEADLINE_CLOSE = "DEADLINE_CLOSE"
    """Task deadline is within 48 hours of the recommended slot."""

    HIGH_PRIORITY = "HIGH_PRIORITY"
    """Task priority is 'high'."""

    MEDIUM_PRIORITY = "MEDIUM_PRIORITY"
    """Task priority is 'medium'."""

    EARLIEST_SLOT = "EARLIEST_SLOT"
    """The recommended slot is the first available among the candidates."""

    MOST_BUFFER_BEFORE_DEADLINE = "MOST_BUFFER_BEFORE_DEADLINE"
    """The recommended slot leaves the most time before the deadline."""

    ONLY_SLOT_AVAILABLE = "ONLY_SLOT_AVAILABLE"
    """Only one candidate slot was provided by the deterministic engine."""

    PROVIDER_FALLBACK = "PROVIDER_FALLBACK"
    """AI provider failed or returned invalid output; the first valid candidate
    was selected deterministically as a safe fallback."""


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
