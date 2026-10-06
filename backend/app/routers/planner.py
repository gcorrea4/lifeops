"""
Planner router — POST /planner/recommend and POST /planner/decision.

The router is intentionally thin:
- DB queries follow the exact same patterns as the existing engine router.
- All business logic lives in app/services/planner.py.
- The deterministic engine service (suggest_slots) is called directly — no
  internal HTTP call to GET /engine/suggest.
- PlannerAgent is instantiated per-request with the injected AbstractProvider.
- One db.commit() per happy path; services never commit.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.agent import PlannerAgent
from app.ai.provider import AbstractProvider, get_provider
from app.core.settings import settings
from app.database import get_db
from app.models.fixed_block import FixedBlock
from app.models.scheduled_slot import ScheduledSlot
from app.models.task import Task, TaskStatus
from app.schemas.planner import (
    DecisionRequest,
    DecisionResponse,
    RecommendRequest,
    RecommendResponse,
    RecommendedSlotOut,
)
from app.services.engine import suggest_slots
from app.services.planner import (
    build_agent_input,
    get_recommendation_or_404,
    persist_recommendation,
    record_decision,
)

router = APIRouter(prefix="/planner", tags=["planner"])

USER_ID = 1  # hardcoded for MVP
LOOKAHEAD_DAYS = 7

_DECISION_MESSAGES = {
    "APPROVED": "Decision recorded. Proceed to POST /engine/book to confirm booking.",
    "MODIFIED": "Decision recorded. Proceed to POST /engine/book to confirm booking.",
    "REJECTED": "Decision recorded. Task remains pending.",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_task_or_404(task_id: int, db: Session) -> Task:
    task = (
        db.query(Task)
        .filter(Task.id == task_id, Task.user_id == USER_ID)
        .first()
    )
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task


# ---------------------------------------------------------------------------
# POST /planner/recommend
# ---------------------------------------------------------------------------


@router.post("/recommend", response_model=RecommendResponse, status_code=201)
def recommend(
    payload: RecommendRequest,
    db: Session = Depends(get_db),
    provider: AbstractProvider = Depends(get_provider),
) -> RecommendResponse:
    """Get an AI-powered slot recommendation for a pending task.

    Flow:
    1. Load and validate the Task (must be pending).
    2. Call the deterministic engine to obtain candidate slots.
    3. If no candidates are available, return 422.
    4. Build AgentInput and run PlannerAgent.recommend().
    5. Persist an AIRecommendation audit row.
    6. Return 201 with the recommendation and the full candidate list.

    Task.status is never mutated here.
    Booking never happens here.
    """
    # 1. Load task
    task = _get_task_or_404(payload.task_id, db)

    # 2. Task must be pending
    if task.status != TaskStatus.pending:
        raise HTTPException(status_code=409, detail="task is not pending")

    # 3. Resolve from_date — default today, reject past (same rule as GET /engine/suggest)
    resolved_from: date = payload.from_date if payload.from_date is not None else date.today()
    if resolved_from < date.today():
        raise HTTPException(status_code=422, detail="from_date cannot be in the past")

    # 4. Load all FixedBlocks for user
    blocks = db.query(FixedBlock).filter(FixedBlock.user_id == USER_ID).all()

    # 5. Load ScheduledSlots in the lookahead window (+1 day for overnight overflow)
    window_start = datetime.combine(resolved_from, settings.WORK_START)
    window_end = datetime.combine(
        resolved_from + timedelta(days=LOOKAHEAD_DAYS + 1),
        settings.WORK_END,
    )
    slots_db = (
        db.query(ScheduledSlot)
        .filter(
            ScheduledSlot.user_id == USER_ID,
            ScheduledSlot.start_datetime < window_end,
            ScheduledSlot.end_datetime > window_start,
        )
        .all()
    )

    # 6. Obtain candidate slots from the deterministic engine (pure function — no HTTP)
    candidate_slots = suggest_slots(
        task=task,
        blocks=blocks,
        slots=slots_db,
        from_date=resolved_from,
        lookahead_days=LOOKAHEAD_DAYS,
        work_start=settings.WORK_START,
        work_end=settings.WORK_END,
    )

    # 7. If no candidates, the AI layer cannot proceed
    if not candidate_slots:
        raise HTTPException(
            status_code=422,
            detail="no candidate slots available for this task",
        )

    # 8. Build agent input and run recommendation
    agent_input = build_agent_input(task, candidate_slots)
    agent = PlannerAgent(provider)
    recommendation = agent.recommend(agent_input)

    # 9. Persist audit row (service adds to session; router commits)
    rec = persist_recommendation(task, candidate_slots, recommendation, provider, db)
    try:
        db.commit()
        db.refresh(rec)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="task no longer exists",
        )

    # 10. Return 201 response
    return RecommendResponse(
        recommendation_id=rec.id,
        task_id=task.id,
        recommended_slot=RecommendedSlotOut(
            start_datetime=rec.recommended_start,
            end_datetime=rec.recommended_end,
        ),
        reason_codes=[code.value for code in recommendation.reason_codes],
        explanation=rec.explanation,
        candidate_slots=candidate_slots,
        fallback_used=rec.fallback_used,
    )


# ---------------------------------------------------------------------------
# POST /planner/decision
# ---------------------------------------------------------------------------


@router.post("/decision", response_model=DecisionResponse, status_code=200)
def decision(
    payload: DecisionRequest,
    db: Session = Depends(get_db),
    provider: AbstractProvider = Depends(get_provider),  # noqa: ARG001 — required by DI graph
) -> DecisionResponse:
    """Record a human decision (APPROVED / MODIFIED / REJECTED) for a recommendation.

    Flow:
    1. Load the AIRecommendation (404 if not found).
    2. Guard against a second decision (409 if already recorded).
    3. Apply the decision via service layer.
    4. Commit and return 200.

    This endpoint NEVER calls /engine/book.
    Task.status is NEVER mutated here.
    Booking remains a separate explicit client action.
    """
    # 1. Load recommendation
    rec = get_recommendation_or_404(payload.recommendation_id, db)

    # 2–3. Apply decision (service handles double-decision guard and MODIFIED validation)
    record_decision(rec, payload.action, payload.chosen_start, payload.chosen_end, db)

    try:
        db.commit()
        db.refresh(rec)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="could not record decision due to a database conflict",
        )

    action_str = rec.user_action.value if hasattr(rec.user_action, "value") else str(rec.user_action)

    return DecisionResponse(
        recommendation_id=rec.id,
        action=action_str,
        final_start=rec.final_start,
        final_end=rec.final_end,
        message=_DECISION_MESSAGES.get(action_str, "Decision recorded."),
    )
