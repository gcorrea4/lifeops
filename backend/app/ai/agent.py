"""
PlannerAgent — AI recommendation layer for LifeOps.

Responsibilities:
- Build a structured prompt from AgentInput (task + deterministic candidate slots).
- Call the injected AbstractProvider.
- Parse and validate the model's JSON response.
- Guard that the returned candidate_id is within bounds.
- Derive reason codes deterministically from task and candidate facts.
- Apply a deterministic fallback (candidates[0]) on any failure.

What this module must NOT do:
- Invent or accept invented datetime strings from the model.
- Trust reason codes from the model — they are derived here, not model-supplied.
- Store or forward raw model output.
- Access the database.
- Make HTTP calls.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from pydantic import BaseModel, Field, ValidationError

from app.ai.provider import AbstractProvider, ProviderError
from app.ai.schemas import (
    AgentInput,
    CandidateSlot,
    PlannerRecommendation,
    ReasonCode,
    RecommendedSlot,
    TaskSummary,
)

_FALLBACK_EXPLANATION = "Default recommendation: first available valid slot selected."


# ---------------------------------------------------------------------------
# Internal raw-output model (used only inside _parse_response)
# ---------------------------------------------------------------------------

class _RawModelOutput(BaseModel):
    """
    Minimal Pydantic model that mirrors exactly what the model should return.
    The model returns only recommended_candidate_id and explanation.
    reason_codes are derived deterministically by the backend; the model does
    not supply them.  Any extra fields the model includes are silently ignored.
    """
    recommended_candidate_id: int = Field(strict=True)
    explanation: str


# ---------------------------------------------------------------------------
# Deterministic reason-code derivation
# ---------------------------------------------------------------------------

def _derive_codes(
    cid: int,
    candidates: list[CandidateSlot],
    task: TaskSummary,
) -> list[ReasonCode]:
    """
    Derive reason codes deterministically from task attributes and the selected
    candidate.  Never relies on model output.

    Rules applied (in order):
    1. Priority code — exactly one of HIGH_PRIORITY / MEDIUM_PRIORITY / LOW_PRIORITY
       always fires based on task.priority.
    2. EARLIEST_SLOT — fires when cid == 0 (engine returns candidates ascending).
    3. ONLY_SLOT_AVAILABLE — fires when len(candidates) == 1.
    4. DEADLINE_CLOSE — fires when task.deadline is not None and
       (deadline - candidates[cid].date).days <= 1, meaning the selected slot
       falls on the deadline date or the calendar day immediately before it.
    """
    codes: list[ReasonCode] = []

    # 1. Priority — exactly one always fires.
    if task.priority == "high":
        codes.append(ReasonCode.HIGH_PRIORITY)
    elif task.priority == "medium":
        codes.append(ReasonCode.MEDIUM_PRIORITY)
    elif task.priority == "low":
        codes.append(ReasonCode.LOW_PRIORITY)

    # 2. Earliest slot.
    if cid == 0:
        codes.append(ReasonCode.EARLIEST_SLOT)

    # 3. Only slot available.
    if len(candidates) == 1:
        codes.append(ReasonCode.ONLY_SLOT_AVAILABLE)

    # 4. Deadline close.
    if task.deadline is not None:
        days_until_deadline = (task.deadline - candidates[cid].date).days
        if days_until_deadline <= 1:
            codes.append(ReasonCode.DEADLINE_CLOSE)

    return codes


# ---------------------------------------------------------------------------
# PlannerAgent
# ---------------------------------------------------------------------------

class PlannerAgent:
    """
    Recommends one candidate slot for a pending task.

    The agent is stateless beyond its injected provider.  It never touches the
    database and never makes autonomous booking decisions.

    The model is asked only to select a candidate_id and provide an explanation.
    All reason codes are derived deterministically by the backend.
    """

    def __init__(self, provider: AbstractProvider) -> None:
        self._provider = provider

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def recommend(self, agent_input: AgentInput) -> PlannerRecommendation:
        """
        Return a PlannerRecommendation for the given AgentInput.

        Precondition: agent_input.candidate_slots must be non-empty.
        Raises ValueError if candidate_slots is empty — the caller is responsible
        for returning an appropriate HTTP 422.

        On any provider or parsing failure the method returns a valid
        PlannerRecommendation with fallback_used=True and candidates[0] as the
        recommended slot.  Raw model output is never surfaced to the caller.
        """
        candidates = agent_input.candidate_slots
        if not candidates:
            raise ValueError("No candidate slots provided to PlannerAgent.recommend().")

        prompt = self._build_prompt(agent_input)

        try:
            raw = self._provider.complete(prompt)
        except ProviderError:
            return self._fallback(candidates)

        recommendation = self._parse_response(raw, agent_input)
        if recommendation is None:
            return self._fallback(candidates)

        return recommendation

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_prompt(self, agent_input: AgentInput) -> str:
        """
        Build a minimal, directive prompt.

        The model is shown:
        - Task attributes (no internal IDs, no PII, no DB fields).
        - Candidate slots as a numbered JSON array with candidate_id, start_datetime,
          and end_datetime.  The model must never reproduce or invent datetimes — it
          returns only the candidate_id integer.
        - The exact JSON structure expected in the response: candidate_id + explanation.
        - An explicit instruction to return ONLY the JSON object, no surrounding prose.

        Reason codes are NOT part of the model output contract.  They are derived
        deterministically by the backend after the candidate_id is validated.
        """
        task = agent_input.task
        deadline_str = task.deadline.isoformat() if task.deadline else "none"

        slots_json = json.dumps(
            [
                {
                    "candidate_id": i,
                    "start_datetime": slot.start_datetime.isoformat(),
                    "end_datetime": slot.end_datetime.isoformat(),
                }
                for i, slot in enumerate(agent_input.candidate_slots)
            ],
            indent=2,
        )

        return (
            "You are a scheduling assistant. Select the best time slot for the task below.\n\n"
            "Task:\n"
            f"- Title: {task.title}\n"
            f"- Duration: {task.duration_minutes} minutes\n"
            f"- Priority: {task.priority}\n"
            f"- Deadline: {deadline_str}\n\n"
            f"Candidate slots:\n{slots_json}\n\n"
            "Return ONLY a JSON object with this exact structure — no text outside the JSON:\n"
            "{\n"
            '  "recommended_candidate_id": <integer index of the chosen slot>,\n'
            '  "explanation": "<one sentence, max 200 characters>"\n'
            "}\n\n"
            "Do not add any text, markdown, or explanation outside the JSON object."
        )

    def _parse_response(
        self,
        raw: str,
        agent_input: AgentInput,
    ) -> Optional[PlannerRecommendation]:
        """
        Parse and validate the model's raw string response.

        Returns a valid PlannerRecommendation, or None on any failure.
        None always triggers the deterministic fallback in recommend().

        Validation steps:
        1. Strip accidental markdown code fences.
        2. JSON decode.
        3. Structural Pydantic validation (requires recommended_candidate_id + explanation).
        4. Bounds check on candidate_id.
        5. Derive reason codes deterministically.
        6. Build and return PlannerRecommendation with fallback_used=False.
        """
        candidates = agent_input.candidate_slots

        try:
            # 1. Strip accidental markdown code fences.
            cleaned = re.sub(r"^```[a-z]*\n?|```$", "", raw.strip(), flags=re.MULTILINE).strip()

            # 2. JSON decode.
            data = json.loads(cleaned)

            # 3. Structural Pydantic validation.
            raw_output = _RawModelOutput.model_validate(data)

            # 4. Bounds check on candidate_id.
            cid = raw_output.recommended_candidate_id
            if cid < 0 or cid >= len(candidates):
                return None

            # 5. Derive reason codes deterministically from task + candidate facts.
            derived_codes = _derive_codes(cid, candidates, agent_input.task)

            # 6. Retrieve the original slot from the deterministic engine output.
            chosen = candidates[cid]

            # 7. Truncate explanation defensively (does not trigger fallback).
            explanation = raw_output.explanation[:200]

            return PlannerRecommendation(
                recommended_slot=RecommendedSlot(
                    start_datetime=chosen.start_datetime,
                    end_datetime=chosen.end_datetime,
                ),
                reason_codes=derived_codes,
                explanation=explanation,
                fallback_used=False,
            )

        except (json.JSONDecodeError, ValidationError, Exception):  # noqa: BLE001
            return None

    def _fallback(self, candidates: list[CandidateSlot]) -> PlannerRecommendation:
        """
        Deterministic fallback: always selects candidates[0].

        The deterministic engine returns candidates ordered by start_datetime
        ascending, so candidates[0] is the earliest valid slot.
        """
        chosen = candidates[0]
        return PlannerRecommendation(
            recommended_slot=RecommendedSlot(
                start_datetime=chosen.start_datetime,
                end_datetime=chosen.end_datetime,
            ),
            reason_codes=[ReasonCode.PROVIDER_FALLBACK],
            explanation=_FALLBACK_EXPLANATION,
            fallback_used=True,
        )
