# LifeOps — ST-8: Planner Service + Router

## Top-Level Overview

**Goal:** Wire the existing `PlannerAgent` and deterministic engine into two new HTTP
endpoints — `POST /api/v1/planner/recommend` and `POST /api/v1/planner/decision` — and
persist every recommendation/decision in the existing `ai_recommendations` table for
auditability.

**Scope:**
- `backend/app/schemas/planner.py` — HTTP request/response schemas.
- `backend/app/services/planner.py` — orchestration layer (engine call → agent call → DB persist).
- `backend/app/routers/planner.py` — the two endpoints.
- `backend/app/main.py` — register the new router.
- `backend/tests/test_planner_router.py` — integration tests through TestClient.

**Non-goals for this sub-task:**
- Automatic booking (never).
- Auditor Agent, feedback learning, user memory.
- Authentication, frontend, ST-9/ST-10.
- Any change to the deterministic engine service or the existing engine router.

**Architecture principle (non-negotiable):**
The deterministic engine is the sole authority for slot validity.
The planner service calls the engine's *internal logic*, not the HTTP endpoint,
and the AI layer only ranks those pre-validated slots.

---

## Design Decisions

### 1. How the service calls the engine

The planner service does **not** make an internal HTTP call to `GET /engine/suggest`.
Instead it calls the same service layer functions that the engine router already calls:
loads `Task`, `FixedBlock`, and `ScheduledSlot` from DB, then calls `suggest_slots()`.
This reuses the deterministic logic without HTTP overhead or circular routing.

### 2. Provider and model_id for audit

`provider` = `settings.AI_PROVIDER` (e.g., `"mock"` or `"watsonx"`).
`model_id` = `settings.WATSONX_MODEL_ID` (always taken from settings, never from model output).

For the `mock` provider `model_id` is stored as `"mock"` — the value in settings is
`"granite-4-1-8b"` which only makes sense for watsonx; so when `AI_PROVIDER == "mock"`,
persist `model_id = "mock"`.

### 3. Serialisation of candidate_slots_json

The candidate slots list returned by `suggest_slots()` is `list[SlotSuggestion]`.
Each item is serialised with `.model_dump(mode="json")` → serialise to JSON string via
`json.dumps()`. Stored in `candidate_slots_json` (TEXT column).
At decision time, deserialise back to compare chosen slot against the stored list.

### 4. Serialisation of reason_codes

`reason_codes` is stored as a JSON string of string values:
`json.dumps([code.value for code in recommendation.reason_codes])`.
Never store enum objects directly.

### 5. MODIFIED slot validation at decision time

Parse `candidate_slots_json` back into a list of dicts.
Compare `chosen_start` / `chosen_end` (from the request) against each entry's
`start_datetime` / `end_datetime` using string-level ISO-8601 comparison after
normalising both sides to `.isoformat()` (naive datetime, no timezone).
If no match: return 422 `"chosen slot is not in the original candidate list"`.

### 6. recommended_start / recommended_end when fallback

`PlannerRecommendation.recommended_slot` is **always** set (fallback also sets it to
`candidates[0]`). Therefore `recommended_start` and `recommended_end` are always non-null
after a successful `recommend()` call. The ORM columns are marked nullable to handle
edge cases but the service always writes a value.

### 7. second-decision guard

Before writing, check `rec.user_action is not None`. If already set: return 409
`"decision already recorded for this recommendation"`.

### 8. Action-specific chosen_start / chosen_end rules

**APPROVED:**
`chosen_start` and `chosen_end` are **not required and are ignored** if sent.
The server always derives `final_start = rec.recommended_start` and
`final_end = rec.recommended_end` from the stored audit row.
This eliminates any risk of the client supplying a tampered slot under APPROVED.

**MODIFIED:**
`chosen_start` and `chosen_end` are **required**.
If either is missing: return 422 `"chosen_start and chosen_end are required for MODIFIED"`.
The chosen slot must exactly match one entry in the stored `candidate_slots_json`
(see Design Decision 5). If not found: return 422 `"chosen slot is not in the original candidate list"`.

**REJECTED:**
`chosen_start` and `chosen_end` are **not required and are ignored** if sent.
`final_start` and `final_end` remain `null`.

### 9. HTTP status codes summary

| Endpoint | Condition | Status |
|---|---|---|
| POST /planner/recommend | success | 201 |
| POST /planner/recommend | task not found | 404 |
| POST /planner/recommend | task not pending | 409 |
| POST /planner/recommend | no candidate slots | 422 |
| POST /planner/decision | success | 200 |
| POST /planner/decision | recommendation not found | 404 |
| POST /planner/decision | decision already recorded | 409 |
| POST /planner/decision | MODIFIED missing chosen_start or chosen_end | 422 |
| POST /planner/decision | MODIFIED slot not in candidate list | 422 |

### 10. Transactions and commits

Each endpoint performs exactly one `db.commit()` at the end of its happy path.
No partial commits. On any exception before commit the session is rolled back by
SQLAlchemy's default session lifecycle (the `get_db` dependency closes the session on
exception without committing).

### 11. IntegrityError

An `IntegrityError` on INSERT (e.g., FK violation if the task was deleted between
the task-load and the insert) is caught and re-raised as 409 or 404 as appropriate.
No special framework needed — standard FastAPI `HTTPException`.

---

## HTTP Schemas (`backend/app/schemas/planner.py`)

### RecommendRequest
```
task_id:   int       (required)
from_date: date      (optional)
```

### RecommendResponse
```
recommendation_id: int
task_id:           int
recommended_slot:
    start_datetime: datetime
    end_datetime:   datetime
reason_codes:     list[str]       (string values, not enum objects)
explanation:      str
candidate_slots:  list[SlotSuggestion]   (full list for frontend display)
fallback_used:    bool
```

### DecisionRequest
```
recommendation_id: int            (required)
action:            UserAction      (APPROVED | MODIFIED | REJECTED)
chosen_start:      datetime        (optional — required only for MODIFIED)
chosen_end:        datetime        (optional — required only for MODIFIED)
```

`chosen_start` / `chosen_end` are typed as `Optional[datetime]` in the schema.
Business validation (required only for MODIFIED, ignored for APPROVED and REJECTED)
is enforced in the service layer, not in the schema, following the existing project pattern.

### DecisionResponse
```
recommendation_id: int
action:            str
final_start:       Optional[datetime]
final_end:         Optional[datetime]
message:           str
```

`message` is always `"Decision recorded. Proceed to POST /engine/book to confirm booking."`
for APPROVED and MODIFIED, and
`"Decision recorded. Task remains pending."` for REJECTED.

---

## Service Layer (`backend/app/services/planner.py`)

### `get_recommendation_or_404(rec_id, db) -> AIRecommendation`
Load `AIRecommendation` filtered by `id` and `user_id == 1`. Raise 404 if not found.

### `build_agent_input(task, slots) -> AgentInput`
Convert `Task` ORM object to `TaskSummary` and `list[SlotSuggestion]` to
`list[CandidateSlot]`. Return `AgentInput`.

### `persist_recommendation(task, slots, recommendation, db) -> AIRecommendation`
Construct `AIRecommendation` ORM object from:
- `task.id`, `user_id=1`
- `provider`: `settings.AI_PROVIDER`
- `model_id`: `settings.WATSONX_MODEL_ID` if `AI_PROVIDER == "watsonx"`, else `"mock"`
- `candidate_slots_json`: `json.dumps([s.model_dump(mode="json") for s in slots])`
- `recommended_start`, `recommended_end`: from `recommendation.recommended_slot`
- `reason_codes`: `json.dumps([c.value for c in recommendation.reason_codes])`
- `explanation`: `recommendation.explanation`
- `fallback_used`: `recommendation.fallback_used`

Add to session. **Do not commit here** — the router commits after this call.

### `record_decision(rec, action, chosen_start, chosen_end, db) -> AIRecommendation`
Apply the decision onto the loaded `AIRecommendation` row:
- Check `rec.user_action is not None` → raise 409
- APPROVED: `final_start = rec.recommended_start`, `final_end = rec.recommended_end`
- MODIFIED: parse `rec.candidate_slots_json`, validate chosen slot is present, set `final_start/end`
- REJECTED: `final_start = None`, `final_end = None`
- Set `rec.user_action = action`

Return updated row (caller commits).

---

## Router (`backend/app/routers/planner.py`)

### `POST /planner/recommend`
1. Load `Task` filtered by `task_id` and `user_id=1` — 404 if not found.
2. Assert `task.status == pending` — 409 if not.
3. Resolve `from_date` (default `date.today()`).
4. Load `FixedBlock` and `ScheduledSlot` lists (same queries as engine router).
5. Call `suggest_slots(task, blocks, slots, ...)` — reuses engine service function.
6. If result is empty — raise 422 `"no candidate slots available for this task"`.
7. Call `build_agent_input(task, slots)`.
8. Instantiate `PlannerAgent(provider)`.
9. Call `agent.recommend(agent_input)`.
10. Call `persist_recommendation(task, slots, recommendation, db)`.
11. `db.commit()` + `db.refresh(rec)`.
12. Return `RecommendResponse`.

### `POST /planner/decision`
1. Load `AIRecommendation` via `get_recommendation_or_404(rec_id, db)`.
2. Guard double-decision → 409.
3. Delegate all action-specific validation and mutation to `record_decision(rec, action, chosen_start, chosen_end, db)`.
4. `db.commit()` + `db.refresh(rec)`.
5. Return `DecisionResponse`.

---

## Registration (`backend/app/main.py`)

Add import and `app.include_router(planner_router, prefix="/api/v1")`.

---

## Integration Tests (`backend/tests/test_planner_router.py`)

### Test class: `TestRecommend`

**Happy paths:**
- `test_recommend_returns_201` — pending task, no blocks → expect 201, valid response shape.
- `test_recommend_persists_audit_row` — verify `AIRecommendation` row exists in DB after call.
- `test_recommend_with_from_date` — optional `from_date` parameter is respected.
- `test_recommend_fallback_used_flag` — mock provider returns invalid JSON → `fallback_used=True`.

**Negative paths:**
- `test_recommend_task_not_found` — 404.
- `test_recommend_task_not_pending` — scheduled task → 409.
- `test_recommend_no_slots` — task with deadline already passed → 422.

### Test class: `TestDecision`

**Happy paths:**
- `test_decision_approved` — APPROVED records `final_start = recommended_start`.
- `test_decision_modified_valid_slot` — MODIFIED with a slot from candidate list → accepted.
- `test_decision_rejected` — REJECTED, `final_start` is null in response.

**Negative paths:**
- `test_decision_not_found` — unknown `recommendation_id` → 404.
- `test_decision_already_recorded` — second POST on same rec → 409.
- `test_decision_approved_ignores_chosen` — APPROVED with `chosen_start/end` supplied → still succeeds and uses `recommended_start/end`, not the supplied values.
- `test_decision_modified_slot_not_in_list` — MODIFIED with invented datetime → 422.
- `test_decision_modified_missing_chosen` — MODIFIED without `chosen_start/end` → 422.

### Test fixture: `mock_provider`
Fixture in `test_planner_router.py` that overrides `get_provider` with a `MockProvider`
returning a valid JSON response picking `candidate_id=0` with `reason_codes=["EARLIEST_SLOT"]`.
Tears down override after test.

---

## Files to Create

| File | Action |
|---|---|
| `backend/app/schemas/planner.py` | Create |
| `backend/app/services/planner.py` | Create |
| `backend/app/routers/planner.py` | Create |
| `backend/tests/test_planner_router.py` | Create |

## Files to Modify

| File | Change |
|---|---|
| `backend/app/main.py` | Import and register `planner_router` |

No other files are modified. The deterministic engine, models, existing routers,
conftest, and AI layer are untouched.

---

## Inconsistency / Integrity Risks

1. **Race condition between recommend and book:** After `/planner/recommend` records
   a slot, availability may change before `/engine/book` is called. This is acceptable
   and expected — `/engine/book` always revalidates. The audit row stores the slot
   recommended *at recommendation time*, not a guarantee of future availability.

2. **Task deleted after recommendation:** If the `Task` is deleted after the
   `AIRecommendation` is created, the FK `ondelete="CASCADE"` removes the audit row
   automatically. The decision endpoint returns 404 naturally.

3. **Multiple recommendations for same pending task:** Nothing prevents calling
   `/planner/recommend` twice on the same task. This is by design — the user may ask
   for a new recommendation at any time. Each produces a separate audit row.
   Only `/engine/book` changes `Task.status`, so the task remains pending between calls.

4. **MODIFIED slot stale by booking time:** The frontend sends `final_start` from the
   decision response to `/engine/book`. The engine revalidates. If the slot is now
   gone (another booking), the engine returns 409. The audit row is already committed
   with the MODIFIED action — this is correct; the decision was made, the booking just
   failed. The task remains pending and the user must call `/planner/recommend` again.

5. **chosen_start / chosen_end timezone:** Store and compare as naive datetimes.
   Strip `tzinfo` on input if present (same pattern as `engine.py`). Comparison uses
   `.isoformat()` string match against the stored `candidate_slots_json`.

---

## Sub-Tasks

---

### ST-8.1 — Planner HTTP Schemas

**Status:** [ ] pending

**Intent:**
Define the Pydantic request/response models that the planner endpoints consume and return.
These live in `backend/app/schemas/planner.py` and are the HTTP contract — separate from
the AI agent schemas in `app/ai/schemas.py`.

**Expected Outcomes:**
- `RecommendRequest`, `RecommendResponse`, `DecisionRequest`, `DecisionResponse` are importable.
- `DecisionRequest.action` uses the existing `UserAction` enum from `app/models/ai_recommendation.py`.
- `RecommendResponse.candidate_slots` uses `SlotSuggestion` from `app/schemas/engine.py`.
- No other files are changed.

**Todo List:**
1. Create `backend/app/schemas/planner.py`.
2. Define `RecommendRequest(BaseModel)` with `task_id: int` and `from_date: Optional[date]`.
3. Define `RecommendedSlotOut(BaseModel)` with `start_datetime` and `end_datetime`.
4. Define `RecommendResponse(BaseModel)` with all fields listed in the Design section.
5. Define `DecisionRequest(BaseModel)` with `recommendation_id`, `action`, `chosen_start`, `chosen_end`.
6. Define `DecisionResponse(BaseModel)` with `recommendation_id`, `action`, `final_start`, `final_end`, `message`.

**Relevant Context:**
- `SlotSuggestion` is in [`backend/app/schemas/engine.py`](backend/app/schemas/engine.py)
- `UserAction` enum is in [`backend/app/models/ai_recommendation.py`](backend/app/models/ai_recommendation.py)
- See "HTTP Schemas" section above for exact field types.

---

### ST-8.2 — Planner Service

**Status:** [ ] pending

**Intent:**
Create the orchestration layer that isolates the router from the details of calling the
engine, constructing the agent input, calling the agent, persisting the audit row, and
applying decisions. The router remains thin; all business logic lives here.

**Expected Outcomes:**
- `build_agent_input()` converts Task ORM + SlotSuggestion list → AgentInput.
- `persist_recommendation()` builds and adds the AIRecommendation ORM row (no commit).
- `record_decision()` validates and applies APPROVED/MODIFIED/REJECTED onto the row (no commit).
- `get_recommendation_or_404()` loads the row or raises 404.
- No database commits inside the service; commit is the router's responsibility.

**Todo List:**
1. Create `backend/app/services/planner.py`.
2. Implement `get_recommendation_or_404(rec_id, db)`.
3. Implement `build_agent_input(task, slots)`.
4. Implement `persist_recommendation(task, slots, recommendation, db)` — builds the ORM object, sets all columns, calls `db.add()`.
5. Implement `record_decision(rec, action, chosen_start, chosen_end, db)` — validates double-decision, validates MODIFIED slot, sets `final_start/end` and `user_action`.

**Relevant Context:**
- Engine suggest logic is in [`backend/app/services/engine.py`](backend/app/services/engine.py) — `suggest_slots()`
- `AgentInput`, `TaskSummary`, `CandidateSlot` are in [`backend/app/ai/schemas.py`](backend/app/ai/schemas.py)
- `AIRecommendation`, `UserAction` are in [`backend/app/models/ai_recommendation.py`](backend/app/models/ai_recommendation.py)
- `settings.AI_PROVIDER` and `settings.WATSONX_MODEL_ID` from [`backend/app/core/settings.py`](backend/app/core/settings.py)
- `candidate_slots_json` is JSON-serialised via `json.dumps` / `json.loads`
- `reason_codes` is JSON-serialised as list of `.value` strings

---

### ST-8.3 — Planner Router

**Status:** [ ] pending

**Intent:**
Expose the two planner HTTP endpoints. The router delegates all business logic to the
service layer and the engine service, keeping itself thin — identical pattern to the
existing engine router.

**Expected Outcomes:**
- `POST /api/v1/planner/recommend` returns 201 with `RecommendResponse`.
- `POST /api/v1/planner/decision` returns 200 with `DecisionResponse`.
- Both endpoints use `Depends(get_db)` and `Depends(get_provider)`.
- The engine's `suggest_slots()` is called directly (no internal HTTP call).
- `PlannerAgent` is instantiated per-request with the injected provider.

**Todo List:**
1. Create `backend/app/routers/planner.py` with `APIRouter(prefix="/planner", tags=["planner"])`.
2. Implement `POST /recommend` — full flow per Design Decisions section.
3. Implement `POST /decision` — full flow per Design Decisions section.
4. Register router in `backend/app/main.py`.

**Relevant Context:**
- `get_provider` dependency is in [`backend/app/ai/provider.py`](backend/app/ai/provider.py)
- Engine router's DB query pattern (blocks + slots window) is in [`backend/app/routers/engine.py`](backend/app/routers/engine.py)
- `LOOKAHEAD_DAYS = 7` and `USER_ID = 1` follow the same constants as engine router
- `suggest_slots()` import from `app.services.engine`
- `main.py` registration pattern: see other router imports in [`backend/app/main.py`](backend/app/main.py)

---

### ST-8.4 — Integration Tests

**Status:** [ ] pending

**Intent:**
Cover the planner router end-to-end via `TestClient` using `MockProvider` dependency
override, SQLite in-memory, and the shared `conftest.py` fixtures. Validate all happy
paths and all negative cases.

**Expected Outcomes:**
- All existing 128 tests continue to pass.
- New test file adds ≥ 12 tests covering the cases listed in the "Integration Tests" section.
- MockProvider override is torn down after each test (no cross-test contamination).
- No real watsonx credentials are required to run the suite.

**Todo List:**
1. Create `backend/tests/test_planner_router.py`.
2. Define `_make_task()` helper (or import from existing test helpers).
3. Define `mock_provider` fixture that overrides `get_provider` and cleans up.
4. Write `TestRecommend` class — happy paths + negative paths.
5. Write `TestDecision` class — happy paths + negative paths.
6. Run full test suite (`pytest backend/`) and confirm 0 failures.

**Relevant Context:**
- Conftest pattern for DB + TestClient: [`backend/tests/conftest.py`](backend/tests/conftest.py)
- Existing router test as style reference: [`backend/tests/test_engine_router.py`](backend/tests/test_engine_router.py)
- `MockProvider` and `get_provider` in [`backend/app/ai/provider.py`](backend/app/ai/provider.py)
- Valid mock JSON response must satisfy `_RawModelOutput`: `{"recommended_candidate_id": 0, "reason_codes": ["EARLIEST_SLOT"], "explanation": "First available slot selected."}`

---

## Completion Criteria

- [ ] `POST /api/v1/planner/recommend` returns 201 and persists an audit row.
- [ ] `POST /api/v1/planner/decision` returns 200 and updates the audit row.
- [ ] MODIFIED with an invented datetime returns 422.
- [ ] Second decision on same recommendation returns 409.
- [ ] No automatic booking in either endpoint.
- [ ] `Task.status` is never mutated by the planner endpoints.
- [ ] All existing tests still pass.
- [ ] At least 12 new tests added.
- [ ] No real watsonx credentials required to run tests.
