"""
Orchestration service for the planner endpoints.

Responsibilities:
- Build AgentInput from a Task ORM object and a list of SlotSuggestion objects.
- Persist a new AIRecommendation audit row (does NOT commit — router commits).
- Record a human decision onto an existing AIRecommendation row (does NOT commit).
- Load an AIRecommendation by id or raise 404.

What this module must NOT do:
- Call db.commit().
- Call PlannerAgent directly (that is the router's job).
- Make HTTP calls.
- Mutate Task.status.
- Trigger booking.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.ai.provider import AbstractProvider
from app.ai.schemas import AgentInput, CandidateSlot, PlannerRecommendation, TaskSummary
from app.models.ai_recommendation import AIRecommendation, UserAction
from app.schemas.engine import SlotSuggestion

USER_ID = 1  # hardcoded for MVP


# ---------------------------------------------------------------------------
# Load helpers
# ---------------------------------------------------------------------------


def get_recommendation_or_404(rec_id: int, db: Session) -> AIRecommendation:
    """Load an AIRecommendation for user_id=1 or raise 404."""
    rec = (
        db.query(AIRecommendation)
        .filter(AIRecommendation.id == rec_id, AIRecommendation.user_id == USER_ID)
        .first()
    )
    if rec is None:
        raise HTTPException(status_code=404, detail="recommendation not found")
    return rec


# ---------------------------------------------------------------------------
# AgentInput construction
# ---------------------------------------------------------------------------


def build_agent_input(task: object, slots: list[SlotSuggestion]) -> AgentInput:
    """Convert a Task ORM object and SlotSuggestion list into an AgentInput.

    Only the fields defined in TaskSummary are forwarded — no internal DB state
    or PII is exposed to the agent.
    """
    task_summary = TaskSummary(
        id=task.id,
        title=task.title,
        duration_minutes=task.duration_minutes,
        priority=str(task.priority.value) if hasattr(task.priority, "value") else str(task.priority),
        deadline=task.deadline,
        status=str(task.status.value) if hasattr(task.status, "value") else str(task.status),
    )
    candidate_slots = [
        CandidateSlot(
            start_datetime=s.start_datetime,
            end_datetime=s.end_datetime,
            date=s.date,
        )
        for s in slots
    ]
    return AgentInput(task=task_summary, candidate_slots=candidate_slots)


# ---------------------------------------------------------------------------
# Audit row persistence
# ---------------------------------------------------------------------------


def persist_recommendation(
    task: object,
    slots: list[SlotSuggestion],
    recommendation: PlannerRecommendation,
    provider: AbstractProvider,
    db: Session,
) -> AIRecommendation:
    """Build and db.add() a new AIRecommendation row.

    Does NOT call db.commit() — the router is responsible for committing.

    provider is the AbstractProvider instance that was actually injected and used
    for this request.  Its provider_name and model_id properties are read directly
    so the audit always reflects the provider that produced the recommendation —
    never a reconstructed value from settings.

    candidate_slots_json stores the full deterministic candidate list so it can
    be used later to validate MODIFIED decisions.

    reason_codes is stored as a stable JSON array of string values.

    Raw model output and chain-of-thought are never stored here.
    """
    # Read audit metadata directly from the injected provider instance.
    provider_name = provider.provider_name
    model_id = provider.model_id

    # Serialise candidate slots as JSON — use mode="json" so datetime/date become ISO-8601 strings.
    candidate_slots_json = json.dumps(
        [s.model_dump(mode="json") for s in slots]
    )

    # Serialise reason codes as a JSON array of their string values.
    reason_codes_json = json.dumps(
        [code.value for code in recommendation.reason_codes]
    )

    rec = AIRecommendation(
        task_id=task.id,
        user_id=USER_ID,
        provider=provider_name,
        model_id=model_id,
        candidate_slots_json=candidate_slots_json,
        recommended_start=recommendation.recommended_slot.start_datetime,
        recommended_end=recommendation.recommended_slot.end_datetime,
        reason_codes=reason_codes_json,
        explanation=recommendation.explanation,
        fallback_used=recommendation.fallback_used,
        # user_action, final_start, final_end are all null until POST /planner/decision
    )
    db.add(rec)
    return rec


# ---------------------------------------------------------------------------
# Decision recording
# ---------------------------------------------------------------------------


def record_decision(
    rec: AIRecommendation,
    action: UserAction,
    chosen_start: Optional[datetime],
    chosen_end: Optional[datetime],
    db: Session,
) -> AIRecommendation:
    """Validate and apply a human decision onto an existing AIRecommendation row.

    Does NOT call db.commit() — the router is responsible for committing.

    Action-specific rules:
      APPROVED  — chosen_start/end are optional and ignored.
                  final_start/end are taken from recommended_start/end.
      MODIFIED  — chosen_start and chosen_end are required (422 if missing).
                  The chosen slot must exactly match one entry in candidate_slots_json (422 if not).
                  final_start/end are set to the validated chosen slot.
      REJECTED  — chosen_start/end are optional and ignored.
                  final_start/end remain null.

    Raises 409 if a decision has already been recorded for this recommendation.
    """
    # Guard: prevent a second decision on the same recommendation.
    if rec.user_action is not None:
        raise HTTPException(
            status_code=409,
            detail="decision already recorded for this recommendation",
        )

    if action == UserAction.APPROVED:
        rec.final_start = rec.recommended_start
        rec.final_end = rec.recommended_end

    elif action == UserAction.MODIFIED:
        # chosen_start and chosen_end are required for MODIFIED.
        if chosen_start is None or chosen_end is None:
            raise HTTPException(
                status_code=422,
                detail="chosen_start and chosen_end are required for MODIFIED",
            )

        # Strip timezone info to match the naive datetimes stored in candidate_slots_json.
        cs = chosen_start.replace(tzinfo=None) if chosen_start.tzinfo is not None else chosen_start
        ce = chosen_end.replace(tzinfo=None) if chosen_end.tzinfo is not None else chosen_end

        # Validate the chosen slot is in the original candidate list.
        candidates: list[dict] = json.loads(rec.candidate_slots_json)
        match_found = any(
            _iso(candidate["start_datetime"]) == cs.isoformat()
            and _iso(candidate["end_datetime"]) == ce.isoformat()
            for candidate in candidates
        )
        if not match_found:
            raise HTTPException(
                status_code=422,
                detail="chosen slot is not in the original candidate list",
            )

        rec.final_start = cs
        rec.final_end = ce

    elif action == UserAction.REJECTED:
        rec.final_start = None
        rec.final_end = None

    rec.user_action = action
    return rec


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _iso(value: str) -> str:
    """Normalise an ISO-8601 datetime string to a canonical naive form.

    The stored candidate_slots_json contains strings like "2026-10-05T08:00:00".
    Parsing and re-serialising strips any sub-second precision differences and
    ensures the comparison is format-independent.
    """
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt.isoformat()
