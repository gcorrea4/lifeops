"""
PlannerAgent — AI recommendation layer for LifeOps.

Responsibilities:
- Build a structured prompt from AgentInput (task + deterministic candidate slots).
- Call the injected AbstractProvider.
- Parse and validate the model's JSON response.
- Guard that the returned candidate_id is within bounds.
- Apply a deterministic fallback (candidates[0]) on any failure.

What this module must NOT do:
- Invent or accept invented datetime strings from the model.
- Accept PROVIDER_FALLBACK as a model-supplied reason code.
- Store or forward raw model output.
- Access the database.
- Make HTTP calls.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from pydantic import BaseModel, ValidationError

from app.ai.provider import AbstractProvider, ProviderError
from app.ai.schemas import (
    AgentInput,
    CandidateSlot,
    PlannerRecommendation,
    ReasonCode,
    RecommendedSlot,
)

# Reason codes the model is allowed to use.
# PROVIDER_FALLBACK is intentionally excluded — it is reserved for system use only.
_ALLOWED_MODEL_CODES: list[str] = [
    code.value
    for code in ReasonCode
    if code is not ReasonCode.PROVIDER_FALLBACK
]

_FALLBACK_EXPLANATION = "Default recommendation: first available valid slot selected."


# ---------------------------------------------------------------------------
# Internal raw-output model (used only inside _parse_response)
# ---------------------------------------------------------------------------

class _RawModelOutput(BaseModel):
    """
    Minimal Pydantic model that mirrors exactly what the model should return.
    Parsed before any business validation so that structural errors are caught
    cleanly via ValidationError rather than KeyError / AttributeError.
    """
    recommended_candidate_id: int
    reason_codes: list[str]
    explanation: str


# ---------------------------------------------------------------------------
# PlannerAgent
# ---------------------------------------------------------------------------

class PlannerAgent:
    """
    Recommends one candidate slot for a pending task.

    The agent is stateless beyond its injected provider.  It never touches the
    database and never makes autonomous booking decisions.
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

        recommendation = self._parse_response(raw, candidates)
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
        - The exact JSON structure expected in the response.
        - The closed list of allowed reason codes (PROVIDER_FALLBACK excluded).
        - An explicit instruction to return ONLY the JSON object, no surrounding prose.
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

        allowed_codes = ", ".join(_ALLOWED_MODEL_CODES)

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
            '  "reason_codes": [<one or more codes from the allowed list>],\n'
            '  "explanation": "<one sentence, max 200 characters>"\n'
            "}\n\n"
            f"Allowed reason_codes values (use only these): {allowed_codes}\n\n"
            "Do not add any text, markdown, or explanation outside the JSON object."
        )

    def _parse_response(
        self,
        raw: str,
        candidates: list[CandidateSlot],
    ) -> Optional[PlannerRecommendation]:
        """
        Parse and validate the model's raw string response.

        Returns a valid PlannerRecommendation, or None on any failure.
        None always triggers the deterministic fallback in recommend().
        """
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

            # 5. Reason code validation — reject unknown strings.
            validated_codes: list[ReasonCode] = []
            for code_str in raw_output.reason_codes:
                try:
                    validated_codes.append(ReasonCode(code_str))
                except ValueError:
                    return None

            # 6. PROVIDER_FALLBACK is reserved for system use; reject if present.
            if ReasonCode.PROVIDER_FALLBACK in validated_codes:
                return None

            # 7. Retrieve the original slot from the deterministic engine output.
            chosen = candidates[cid]

            # 8. Truncate explanation defensively (does not trigger fallback).
            explanation = raw_output.explanation[:200]

            return PlannerRecommendation(
                recommended_slot=RecommendedSlot(
                    start_datetime=chosen.start_datetime,
                    end_datetime=chosen.end_datetime,
                ),
                reason_codes=validated_codes,
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
