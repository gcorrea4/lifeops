"""
HTTP request/response schemas for the planner endpoints.

These are the HTTP contract only — separate from the AI agent schemas in app/ai/schemas.py.

POST /api/v1/planner/recommend
POST /api/v1/planner/decision
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.ai_recommendation import UserAction
from app.schemas.engine import SlotSuggestion


# ---------------------------------------------------------------------------
# POST /planner/recommend — request
# ---------------------------------------------------------------------------


class RecommendRequest(BaseModel):
    task_id: int
    from_date: Optional[date] = None


# ---------------------------------------------------------------------------
# POST /planner/recommend — response
# ---------------------------------------------------------------------------


class RecommendedSlotOut(BaseModel):
    """The single slot the agent chose — taken verbatim from the stored audit row."""

    model_config = ConfigDict(from_attributes=False)

    start_datetime: datetime
    end_datetime: datetime


class RecommendResponse(BaseModel):
    """Response body for POST /planner/recommend (HTTP 201).

    candidate_slots is the full deterministic list associated with this
    specific recommendation.  The frontend must use this list when presenting
    alternatives — it must NOT call GET /engine/suggest again, because a fresh
    call could reflect a different system state.
    """

    model_config = ConfigDict(from_attributes=False)

    recommendation_id: int
    task_id: int
    recommended_slot: RecommendedSlotOut
    reason_codes: list[str]           # string values, never enum objects
    explanation: str
    candidate_slots: list[SlotSuggestion]  # full list for frontend display
    fallback_used: bool


# ---------------------------------------------------------------------------
# POST /planner/decision — request
# ---------------------------------------------------------------------------


class DecisionRequest(BaseModel):
    """Request body for POST /planner/decision.

    chosen_start / chosen_end semantics per action:
      APPROVED  — optional, ignored; final slot is taken from recommended_start/end.
      MODIFIED  — required; must exactly match one candidate in the stored candidate list.
      REJECTED  — optional, ignored; final slot stays null.

    Business validation is enforced in the service layer, not here.
    """

    recommendation_id: int
    action: UserAction
    chosen_start: Optional[datetime] = None
    chosen_end: Optional[datetime] = None


# ---------------------------------------------------------------------------
# POST /planner/decision — response
# ---------------------------------------------------------------------------


class DecisionResponse(BaseModel):
    """Response body for POST /planner/decision (HTTP 200)."""

    model_config = ConfigDict(from_attributes=False)

    recommendation_id: int
    action: str
    final_start: Optional[datetime]
    final_end: Optional[datetime]
    message: str
