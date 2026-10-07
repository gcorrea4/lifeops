# Deterministic Reason-Code Derivation Plan

## Status: [ ] pending

## Overview

### Goal
Replace model-supplied reason codes with backend-derived deterministic codes. The model
continues to select a candidate_id and provide a free-text explanation. The backend derives
every reason code from verifiable facts after validating the candidate_id. This eliminates
the class of semantically incorrect codes (e.g. EARLIEST_SLOT on candidate_id=6) without
triggering fallback on an otherwise valid candidate selection.

### Scope
- `backend/app/ai/schemas.py`
- `backend/app/ai/agent.py`
- `backend/tests/test_planner_agent.py`
- `backend/tests/test_planner_router.py`

No DB migration, no endpoint changes, no frontend changes, no new dependencies.

### Invariants preserved
- Fallback still fires for: ProviderError, malformed JSON, missing recommended_candidate_id
  field, candidate_id out of bounds.
- PROVIDER_FALLBACK is still system-only and appears only in the fallback path.
- Raw model output is never stored.
- Audit record reason_codes remain a JSON array of string values in the same column.
- HTTP response shape (reason_codes: list[str]) is unchanged.
- Frontend receives reason_codes exactly as before.

---

## Reason-Code Derivation Rules

All rules are evaluated after a valid candidate_id is confirmed.
`task` refers to TaskSummary (already in AgentInput).
`candidates` refers to the full list from AgentInput.
`cid` is the validated integer candidate_id.

| Code | Rule | Notes |
|---|---|---|
| HIGH_PRIORITY | task.priority == "high" | Always deterministic |
| MEDIUM_PRIORITY | task.priority == "medium" | Always deterministic |
| EARLIEST_SLOT | cid == 0 | Engine returns ascending order; index 0 is definitionally earliest |
| ONLY_SLOT_AVAILABLE | len(candidates) == 1 | Trivial count |
| DEADLINE_CLOSE | task.deadline is not None and (task.deadline - candidates[cid].date).days <= 1 | Same calendar day or next day; calendar-date subtraction only, no wall-clock |
| PROVIDER_FALLBACK | system-only; never derived here | Remains in fallback path unchanged |
| MOST_BUFFER_BEFORE_DEADLINE | **REMOVED** | Redundant with EARLIEST_SLOT under correct interpretation; model demonstrated confusion; removal is safer |

Multiple codes can apply simultaneously (e.g. HIGH_PRIORITY + EARLIEST_SLOT + DEADLINE_CLOSE).

An empty code list is valid and honest: it means no categorical rule fired (e.g. low-priority
task, cid != 0, no deadline, len(candidates) > 1). The explanation field still supplies AI
reasoning.

---

## Sub-Tasks

---

### Sub-Task 1: Update ReasonCode enum in schemas.py

**Status:** [ ] pending

**Intent**
Remove MOST_BUFFER_BEFORE_DEADLINE from the ReasonCode enum. Update docstrings to reflect
that all remaining codes (except PROVIDER_FALLBACK) are now derived deterministically by
the backend, not supplied by the model.

**Expected Outcomes**
- `ReasonCode.MOST_BUFFER_BEFORE_DEADLINE` no longer exists.
- The enum has six members: DEADLINE_CLOSE, HIGH_PRIORITY, MEDIUM_PRIORITY, EARLIEST_SLOT,
  ONLY_SLOT_AVAILABLE, PROVIDER_FALLBACK.
- Docstrings accurately state each code is deterministically derived.

**Todo List**
1. In `backend/app/ai/schemas.py`, remove the `MOST_BUFFER_BEFORE_DEADLINE` enum member and
   its docstring.
2. Update the class-level docstring of `ReasonCode` to state that all codes except
   PROVIDER_FALLBACK are derived by the backend after the model selects a candidate_id.
3. Update per-member docstrings to say "applied when" rather than "the model uses this when".

**Relevant Context**
- File: `backend/app/ai/schemas.py`, class `ReasonCode` (lines 24–50).
- No other file imports MOST_BUFFER_BEFORE_DEADLINE directly (it is used only via the enum
  in agent.py and tests).

---

### Sub-Task 2: Refactor PlannerAgent in agent.py

**Status:** [ ] pending

**Intent**
1. Remove `_ALLOWED_MODEL_CODES` constant (no longer needed — model no longer supplies codes).
2. Simplify `_RawModelOutput`: remove `reason_codes: list[str]` field. The model output
   schema now requires only `recommended_candidate_id: int` and `explanation: str`.
3. Simplify `_build_prompt`: remove the reason_codes line from the response template and
   remove the "Allowed reason_codes values" line. The model is now asked for only two fields.
4. Refactor `_parse_response`: remove steps 5 (reason-code validation loop) and 6
   (PROVIDER_FALLBACK guard). After step 4 (bounds check), call `_derive_codes` to produce
   the code list.
5. Add `_derive_codes` as a module-level pure function. It takes `cid`, `candidates`,
   and `task` and returns `list[ReasonCode]`.
6. Update `_parse_response` signature to accept `agent_input` instead of only `candidates`,
   so `_derive_codes` has access to `task`.
7. Update `recommend()` to pass `agent_input` to `_parse_response`.

**Expected Outcomes**
- `_RawModelOutput` has two fields: `recommended_candidate_id: int`, `explanation: str`.
- `_build_prompt` no longer mentions reason_codes or allowed codes list.
- `_parse_response` no longer validates reason codes from the model.
- `_derive_codes` is a standalone pure function that can be unit-tested directly.
- Fallback triggers are unchanged: ProviderError, JSONDecodeError, ValidationError (missing
  recommended_candidate_id or explanation), candidate_id out of bounds.
- An extra model field (e.g. reason_codes still present in model output) is tolerated by
  Pydantic by default (extra fields are ignored in model_validate). No extra guard needed.

**Todo List**
1. Delete `_ALLOWED_MODEL_CODES` constant and its comment block.
2. Remove `reason_codes: list[str]` from `_RawModelOutput`.
3. In `_build_prompt`, remove:
   - The `reason_codes` line from the JSON object template.
   - The `allowed_codes = ", ".join(...)` line.
   - The "Allowed reason_codes values" instruction line.
   Update the template comment to say the model returns only candidate_id and explanation.
4. Change `_parse_response(self, raw, candidates)` signature to
   `_parse_response(self, raw, agent_input)`. Extract `candidates = agent_input.candidate_slots`
   at the top.
5. Remove steps 5 and 6 from `_parse_response` (lines 189–198 in current file).
6. After step 4 (bounds check), add: `derived_codes = _derive_codes(cid, candidates, agent_input.task)`.
7. Replace `reason_codes=validated_codes` in the PlannerRecommendation constructor with
   `reason_codes=derived_codes`.
8. Update the call in `recommend()`: `self._parse_response(raw, agent_input)` instead of
   `self._parse_response(raw, candidates)`.
9. Add `_derive_codes` module-level function implementing the five rules from the table above.

**_derive_codes implementation (precise)**
```
def _derive_codes(
    cid: int,
    candidates: list[CandidateSlot],
    task: TaskSummary,
) -> list[ReasonCode]:
    codes: list[ReasonCode] = []
    if task.priority == "high":
        codes.append(ReasonCode.HIGH_PRIORITY)
    if task.priority == "medium":
        codes.append(ReasonCode.MEDIUM_PRIORITY)
    if cid == 0:
        codes.append(ReasonCode.EARLIEST_SLOT)
    if len(candidates) == 1:
        codes.append(ReasonCode.ONLY_SLOT_AVAILABLE)
    if task.deadline is not None:
        days_until_deadline = (task.deadline - candidates[cid].date).days
        if days_until_deadline <= 1:
            codes.append(ReasonCode.DEADLINE_CLOSE)
    return codes
```

**Relevant Context**
- File: `backend/app/ai/agent.py`, all sections.
- `TaskSummary.priority` is a plain string (e.g. "high", "medium", "low") at this layer.
  See `services/planner.py` lines 67–69 where it is normalised from the ORM enum value.
- `CandidateSlot.date` is a `datetime.date` object. `TaskSummary.deadline` is
  `Optional[datetime.date]`. The subtraction `deadline - candidates[cid].date` yields a
  `timedelta`; `.days` is an integer.

---

### Sub-Task 3: Update test_planner_agent.py

**Status:** [ ] pending

**Intent**
Update unit tests to reflect:
- Mock provider responses no longer include reason_codes.
- Tests that checked fallback for unknown codes or PROVIDER_FALLBACK in model output are
  removed (those paths no longer exist).
- Tests that checked reason_codes from the model response now check derived codes.
- New direct unit tests for `_derive_codes`.

**Expected Outcomes**
- All existing tests that are still valid pass without modification of the logic under test.
- Two tests removed: `test_recommend_fallback_unknown_reason_code` and
  `test_recommend_fallback_provider_fallback_in_output`.
- `_valid_response` helper no longer includes reason_codes in the JSON.
- `test_recommend_valid_response` asserts derived codes (HIGH_PRIORITY, DEADLINE_CLOSE
  based on the _task() fixture: priority="high", deadline=date(2026,10,10), cid=1, two slots).
  Wait — with two slots and cid=1, EARLIEST_SLOT does NOT fire. DEADLINE_CLOSE fires only if
  (date(2026,10,10) - date(2026,10,5)).days <= 1 → 5 days → does NOT fire for _slot(5, 14).
  So for the existing happy-path test (cid=1, priority="high"), only HIGH_PRIORITY fires.
  The test must be updated to assert `ReasonCode.HIGH_PRIORITY in result.reason_codes`.
- New tests for `_derive_codes` cover all five rules and combinations.

**Todo List**
1. Update `_valid_response()` helper: remove the `reason_codes` key from the JSON dict.
   The model response is now `{"recommended_candidate_id": ..., "explanation": "..."}`.
2. Remove `test_recommend_fallback_unknown_reason_code` (no longer a fallback trigger).
3. Remove `test_recommend_fallback_provider_fallback_in_output` (same reason).
4. Update `test_recommend_valid_response`: replace assertions on DEADLINE_CLOSE and
   HIGH_PRIORITY from model output with assertions on deterministically derived codes.
   For cid=1, priority="high", deadline=date(2026,10,10), slot date=2026-10-05:
   - deadline delta = 5 days → DEADLINE_CLOSE does NOT fire
   - HIGH_PRIORITY fires (priority="high")
   - cid=1 → EARLIEST_SLOT does NOT fire
   - 2 candidates → ONLY_SLOT_AVAILABLE does NOT fire
   Assert: `result.reason_codes == [ReasonCode.HIGH_PRIORITY]`
5. Update `test_recommend_only_slot_available`: mock response no longer has reason_codes.
   Assert: `ReasonCode.ONLY_SLOT_AVAILABLE in result.reason_codes` (still valid, now derived).
6. Update `test_recommend_json_with_code_fences`: mock response inside fences no longer has
   reason_codes.
7. Update `test_recommend_explanation_truncated`: mock response no longer has reason_codes.
8. Add new test group `TestDeriveCodes` covering:
   - `test_derive_codes_high_priority`: cid=0, 2 candidates, priority="high", no deadline →
     codes contain HIGH_PRIORITY and EARLIEST_SLOT.
   - `test_derive_codes_medium_priority`: cid=1, 2 candidates, priority="medium", no deadline →
     codes contain MEDIUM_PRIORITY only.
   - `test_derive_codes_low_priority_no_codes`: cid=1, 2 candidates, priority="low", no deadline →
     codes is empty list.
   - `test_derive_codes_only_slot`: cid=0, 1 candidate, priority="high", no deadline →
     codes contain HIGH_PRIORITY, EARLIEST_SLOT, ONLY_SLOT_AVAILABLE.
   - `test_derive_codes_deadline_close_today`: cid=0, 1 candidate, slot date=X,
     deadline=X (same day) → DEADLINE_CLOSE fires (0 days).
   - `test_derive_codes_deadline_close_tomorrow`: slot date=X, deadline=X+1 → DEADLINE_CLOSE
     fires (1 day).
   - `test_derive_codes_deadline_not_close`: slot date=X, deadline=X+5 → DEADLINE_CLOSE does
     not fire.
   - `test_derive_codes_no_deadline`: deadline=None → DEADLINE_CLOSE does not fire.

**Relevant Context**
- Import `_derive_codes` from `app.ai.agent` in the test file for direct unit tests.
- `_derive_codes` is a module-level function; it can be imported and called directly without
  a PlannerAgent instance.

---

### Sub-Task 4: Update test_planner_router.py

**Status:** [ ] pending

**Intent**
Update the integration test mock response and assertions to match the new prompt/output
contract where the model response no longer includes reason_codes.

**Expected Outcomes**
- `_VALID_MOCK_RESPONSE` does not include reason_codes.
- Assertions on reason_codes values in recommend tests reflect deterministic derivation.
- The test task must have known priority so assertions on codes are deterministic.

**Todo List**
1. Update `_VALID_MOCK_RESPONSE`: remove the `reason_codes` field from the JSON. New value:
   ```python
   _VALID_MOCK_RESPONSE = json.dumps({
       "recommended_candidate_id": 0,
       "explanation": "First available slot selected.",
   })
   ```
2. In `test_recommend_returns_201`: the assertion `len(body["reason_codes"]) > 0` assumes at
   least one code is derived. The test task uses `_make_task()` defaults. Check what
   `_make_task()` sets for priority: it uses `Priority.medium` (from conftest). With cid=0
   and medium priority, `MEDIUM_PRIORITY` and `EARLIEST_SLOT` both fire. So the assertion
   `len(body["reason_codes"]) > 0` remains valid. No change needed there.
3. In `test_recommend_persists_audit_row`: the assertion `len(reason_codes) > 0` is valid for
   the same reason. No change needed.
4. In `test_recommend_fallback_used_flag_on_invalid_provider_response`: no change needed
   (only checks fallback_used=True).
5. Review `_make_recommendation` fixture in TestDecision (line 227): it uses
   `_VALID_MOCK_RESPONSE` indirectly. After step 1, the mock response changes but the fixture
   still gets a 201. Verify the tests in TestDecision do not assert specific reason_code
   values (they assert on action/final_start/final_end — no change needed).
6. Review `TestAuditMetadata`: those tests check provider and model_id fields. No reason_codes
   assertions present. No change needed.

**Relevant Context**
- File: `backend/tests/test_planner_router.py`, lines 28–34 (_VALID_MOCK_RESPONSE) and
  lines 91–217 (TestRecommend).

---

## Files Changed (complete list)

| File | Nature of change |
|---|---|
| `backend/app/ai/schemas.py` | Remove MOST_BUFFER_BEFORE_DEADLINE enum member; update docstrings |
| `backend/app/ai/agent.py` | Remove _ALLOWED_MODEL_CODES; simplify _RawModelOutput; simplify prompt; refactor _parse_response; add _derive_codes |
| `backend/tests/test_planner_agent.py` | Remove 2 tests; update 5 tests; add ~8 new _derive_codes tests |
| `backend/tests/test_planner_router.py` | Update _VALID_MOCK_RESPONSE; minor assertion review |

## Files NOT changed

| File | Reason |
|---|---|
| `backend/app/services/planner.py` | persist_recommendation stores recommendation.reason_codes unchanged |
| `backend/app/routers/planner.py` | No change to HTTP contract |
| `backend/app/routers/engine.py` | No change |
| `backend/app/models/ai_recommendation.py` | reason_codes column stores JSON strings unchanged |
| `backend/app/schemas/planner.py` | HTTP contract: reason_codes: list[str] unchanged |
| `frontend/src/api/types.ts` | reason_codes: string[] unchanged |
| `frontend/src/components/PlannerPanel.tsx` | No change |
| All other backend tests | Not affected |
| Docker, requirements, .env | No change |

---

## Validation

After implementation, run:
```
docker compose exec -T -e WATSONX_API_KEY= api python -m pytest tests -q -p no:cacheprovider
```

Expected: 186+ passed (net of 2 removed tests + new tests), 1 skipped, 0 failed.

The removed tests (`test_recommend_fallback_unknown_reason_code`,
`test_recommend_fallback_provider_fallback_in_output`) covered paths that no longer exist;
their removal reduces total count by 2. New _derive_codes tests add ~8.
Net expected: approximately 192 passed, 1 skipped, 0 failed.
