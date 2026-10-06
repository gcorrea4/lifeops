# LifeOps — Week 2 Plan: AI Decision Layer

## Top-Level Overview

**Goal:** Add an explainable AI recommendation layer on top of the existing deterministic
availability engine. The Planner Agent receives valid candidate slots from the engine,
ranks them, picks one, and returns a structured recommendation with reason codes and a
short human-readable explanation. The user then approves, modifies, or rejects the
recommendation. Booking only happens through the existing deterministic
`POST /engine/book` endpoint after explicit user confirmation.

**Scope:**
- Planner Agent backend service (IBM watsonx / Granite as primary provider).
- Provider abstraction so the application is not coupled to the watsonx SDK.
- New `POST /api/v1/planner/recommend` endpoint.
- New `ai_recommendations` database table for audit trail.
- `POST /api/v1/planner/decision` endpoint to record human Approve / Modify / Reject.
- Pydantic schemas for agent input, agent output, and decision recording.
- Unit tests with mocked provider — no real watsonx credentials required.
- Integration tests through TestClient.

**Out of scope (Week 2):**
- Auditor Agent.
- User memory or user profiles.
- Embeddings, vector database, RAG.
- Model fine-tuning or training.
- Redis, Celery, background jobs.
- Authentication or multi-user support.
- Additional AI providers (Gemini requires explicit approval).
- Autonomous booking without user confirmation.

**Architecture principle (non-negotiable):**
The deterministic engine is the sole authority for slot validity.
The AI layer receives only slots that have already passed deterministic validation.
The AI layer may rank and explain — it may not create, invent, or bypass.

---

## Architecture

```
Frontend / API Client
        |
        | POST /api/v1/planner/recommend
        v
[PlannerRouter]
        |
        |-- calls GET /engine/suggest (internally) to obtain valid candidate slots
        |-- loads Task from DB
        |-- calls PlannerAgent.recommend(task, slots)
        |      |
        |      |-- builds structured prompt
        |      |-- calls ProviderClient.complete(prompt)
        |      |-- validates JSON response
        |      |-- guards: recommended slot must be in candidate list
        |      |-- returns PlannerRecommendation
        |
        |-- persists ai_recommendations row (audit)
        |-- returns PlannerRecommendation to client
        |
        | POST /api/v1/planner/decision
        v
[PlannerRouter]
        |-- loads ai_recommendations row
        |-- records user action: APPROVED / MODIFIED / REJECTED
        |-- APPROVED: records recommended slot as final_slot; client then calls POST /engine/book
        |-- MODIFIED: validates chosen slot exists in candidate_slots_json of that row;
        |             records chosen slot as final_slot; client then calls POST /engine/book
        |-- REJECTED: no final_slot; no booking
        |-- updates ai_recommendations.user_action + final_slot
        |   (decision endpoint NEVER calls /engine/book automatically)
```

```
backend/app/
  ai/
    __init__.py
    agent.py          # PlannerAgent — prompt construction + output validation
    provider.py       # AbstractProvider + WatsonxProvider + MockProvider
    schemas.py        # AgentInput, PlannerRecommendation, ReasonCode enum
  models/
    ai_recommendation.py   # SQLAlchemy model for audit table
  schemas/
    planner.py        # RecommendRequest, DecisionRequest, RecommendResponse
  routers/
    planner.py        # POST /planner/recommend, POST /planner/decision
  services/
    planner.py        # Orchestration: call engine, call agent, persist
```

---

## Reason Codes

Initial enum (`ReasonCode`):

| Code | Meaning |
|---|---|
| `DEADLINE_CLOSE` | Task deadline is within 48 hours of the recommended slot |
| `HIGH_PRIORITY` | Task priority is `high` |
| `MEDIUM_PRIORITY` | Task priority is `medium` |
| `EARLIEST_SLOT` | The recommended slot is the first available among candidates |
| `MOST_BUFFER_BEFORE_DEADLINE` | The recommended slot leaves the most time before deadline |
| `ONLY_SLOT_AVAILABLE` | Only one candidate slot was provided |
| `PROVIDER_FALLBACK` | AI provider failed; first valid slot selected automatically |

---

## Agent Input Schema

```json
{
  "task": {
    "id": 1,
    "title": "Study for Algorithms exam",
    "duration_minutes": 90,
    "priority": "high",
    "deadline": "2026-10-07",
    "status": "pending"
  },
  "candidate_slots": [
    {
      "start_datetime": "2026-10-05T08:00:00",
      "end_datetime":   "2026-10-05T09:30:00",
      "date": "2026-10-05"
    }
  ]
}
```

The candidate slots list is the exact output of `GET /engine/suggest` — already validated
and capped at 10. No additional fields are added to avoid prompt bloat.

---

## Agent Output Schema (Structured JSON — returned by model)

```json
{
  "recommended_slot": {
    "start_datetime": "2026-10-05T08:00:00",
    "end_datetime":   "2026-10-05T09:30:00"
  },
  "reason_codes": ["DEADLINE_CLOSE", "HIGH_PRIORITY", "EARLIEST_SLOT"],
  "explanation": "This slot is recommended because the task has a close deadline, high priority, and this is the earliest available window."
}
```

Chain-of-thought is never stored. The model is instructed to return only the JSON object
above — no prose outside the JSON boundaries.

---

## Audit Trail Schema (ai_recommendations table)

| Column | Type | Notes |
|---|---|---|
| `id` | INT PK autoincrement | |
| `task_id` | INT FK → tasks | |
| `user_id` | INT | hardcoded 1 for Week 2 |
| `created_at` | DATETIME | server default now() |
| `provider` | VARCHAR(64) | e.g. `"watsonx"` or `"mock"` |
| `model_id` | VARCHAR(128) | e.g. `"granite-4-1-8b"` — stored at request time from `settings.WATSONX_MODEL_ID` |
| `candidate_slots_json` | TEXT | JSON array of SlotSuggestion objects |
| `recommended_start` | DATETIME | nullable — null if provider failed |
| `recommended_end` | DATETIME | nullable — null if provider failed |
| `reason_codes` | TEXT | JSON array of strings |
| `explanation` | TEXT | Short human-readable string |
| `fallback_used` | BOOLEAN | True if deterministic fallback triggered |
| `user_action` | ENUM | `APPROVED`, `MODIFIED`, `REJECTED`, null (pending) |
| `final_start` | DATETIME | nullable — the slot that was ultimately sent to /engine/book |
| `final_end` | DATETIME | nullable |

Sensitive model internals (chain-of-thought, raw completion) are never stored.

---

## API Endpoints

### POST /api/v1/planner/recommend

**Request body:**
```json
{
  "task_id": 1,
  "from_date": "2026-10-05"  // optional
}
```

**Response (200):**
```json
{
  "recommendation_id": 42,
  "task_id": 1,
  "recommended_slot": {
    "start_datetime": "...",
    "end_datetime": "..."
  },
  "reason_codes": ["DEADLINE_CLOSE", "HIGH_PRIORITY"],
  "explanation": "...",
  "candidate_slots": [...],
  "fallback_used": false
}
```

**Error cases:**
- `404` — task not found
- `409` — task is not pending
- `422` — no candidate slots available (engine returned empty list)

### POST /api/v1/planner/decision

**Request body:**
```json
{
  "recommendation_id": 42,
  "action": "APPROVED",                  // APPROVED | MODIFIED | REJECTED
  "chosen_start": "2026-10-05T08:00:00", // required when APPROVED or MODIFIED
  "chosen_end":   "2026-10-05T09:30:00"  // required when APPROVED or MODIFIED
}
```

**Response (200):**
```json
{
  "recommendation_id": 42,
  "action": "APPROVED",
  "message": "Decision recorded. Proceed to POST /engine/book to confirm booking."
}
```

**MODIFIED validation rule:**
`chosen_start` / `chosen_end` must exactly match one of the `candidate_slots` that were
returned in the original `RecommendResponse` for this `recommendation_id`.
Arbitrary datetimes are not accepted. If the chosen slot is not found in the stored
candidate list: return `422 "chosen slot is not in the original candidate list"`.

**Error cases:**
- `404` — recommendation_id not found
- `409` — decision already recorded for this recommendation
- `422` — APPROVED or MODIFIED but chosen_start/chosen_end missing
- `422` — MODIFIED with a slot not in the original candidate list

**Important:** This endpoint records the human decision only.
Booking still requires a separate explicit `POST /engine/book` call by the client.
This enforces deterministic revalidation and preserves the human-in-the-loop contract:
recommend → decision → /engine/book are always three distinct actions.

---

## Provider Abstraction

```python
# backend/app/ai/provider.py

from abc import ABC, abstractmethod

class AbstractProvider(ABC):
    @abstractmethod
    def complete(self, prompt: str) -> str:
        """Send prompt, return raw string response."""

class WatsonxProvider(AbstractProvider):
    def complete(self, prompt: str) -> str:
        # Uses ibm-watsonx-ai SDK
        # Reads WATSONX_API_KEY, WATSONX_PROJECT_ID, WATSONX_URL, WATSONX_MODEL_ID from settings

class MockProvider(AbstractProvider):
    def __init__(self, fixed_response: str):
        self._response = fixed_response
    def complete(self, prompt: str) -> str:
        return self._response
```

The active provider is selected by the `AI_PROVIDER` environment variable:
- `"watsonx"` → `WatsonxProvider`
- `"mock"` → `MockProvider` (used only in tests, never in production)

The router/service never imports the concrete provider directly —
it receives an `AbstractProvider` instance via a FastAPI dependency.

---

## Environment Variables

New additions to `.env.exemple` and `Settings`:

| Variable | Default | Purpose |
|---|---|---|
| `AI_PROVIDER` | `"mock"` | Active provider (`watsonx` in production) |
| `WATSONX_API_KEY` | `""` | IBM watsonx API key |
| `WATSONX_PROJECT_ID` | `""` | watsonx project ID |
| `WATSONX_URL` | `"https://us-south.ml.cloud.ibm.com"` | watsonx endpoint |
| `WATSONX_MODEL_ID` | `"granite-4-1-8b"` | Model identifier — configurable; never hardcoded in application code |

These values are never committed. Tests use `MockProvider` and require no real credentials.

---

## Invalid Output Handling

### Model returns malformed JSON
The agent catches `json.JSONDecodeError` and `pydantic.ValidationError`.
On parse failure: activate fallback (see below). Log the raw response for debugging.
Never propagate raw model output to the user.

### Model recommends a slot not in the candidate list
After parsing the model's JSON, validate that `recommended_slot.start_datetime`
matches one of the candidate slots. If not found: activate fallback.
This guard ensures the AI cannot invent unavailable times.

### Fallback behavior
When fallback activates:
1. Select the first slot from the candidate list (earliest by `start_datetime`).
2. Apply reason code `PROVIDER_FALLBACK`.
3. Set `fallback_used = True` in the audit row.
4. Return a valid recommendation to the user — the flow is never broken.

Fallback is deterministic and always safe because all candidates were already
validated by the deterministic engine.

### AI provider network/API failure
`WatsonxProvider.complete()` wraps the SDK call in a try/except.
On `Exception`: raise a domain-specific `ProviderError`.
`PlannerAgent.recommend()` catches `ProviderError` and triggers fallback.
The HTTP response is still 200 with `fallback_used = True`.
A 500 is only raised if the candidate list itself is empty (no fallback target).

---

## Human-in-the-Loop Flow

```
POST /planner/recommend
    → returns recommendation_id + recommended_slot + reason_codes + explanation + candidate_slots

User reads explanation and candidate list
    → chooses: APPROVED | MODIFIED | REJECTED

POST /planner/decision
    → APPROVED: records recommended slot as final_slot
    → MODIFIED: validates chosen slot is in candidate_slots list for this recommendation_id;
                records chosen slot as final_slot
    → REJECTED: records action; no final_slot
    → returns message: "Decision recorded. Proceed to POST /engine/book to confirm booking."
    → does NOT call /engine/book automatically

If APPROVED or MODIFIED:
    (client makes a separate explicit call)
    POST /engine/book { task_id, start_datetime: final_start }
    → full deterministic revalidation
    → ScheduledSlot created
    → Task.status = scheduled

If REJECTED:
    No booking. Task remains pending.
    User may call POST /planner/recommend again.
```

The booking step is always a separate, explicit client action.
The decision endpoint never triggers booking automatically.
The AI recommendation never bypasses the deterministic engine.
All three steps — recommend, decision, book — are intentionally independent.

---

## Sub-Tasks

---

### ST-6 — AI Layer Foundation

**Status:** [ ] pending

**Intent:**
Establish the foundation that all other AI sub-tasks depend on:
provider abstraction, reason codes enum, agent input/output schemas,
new environment variables, and the `ai_recommendations` database table.

**Expected Outcomes:**
- `backend/app/ai/__init__.py`, `backend/app/ai/provider.py`, `backend/app/ai/schemas.py` exist.
- `AbstractProvider`, `WatsonxProvider`, `MockProvider` are importable.
- `ReasonCode` enum with all 7 initial codes is defined.
- `AgentInput` and `PlannerRecommendation` Pydantic models are defined.
- `AIRecommendation` SQLAlchemy model exists and maps to `ai_recommendations` table.
- `backend/app/core/settings.py` gains `AI_PROVIDER`, `WATSONX_API_KEY`, `WATSONX_PROJECT_ID`, `WATSONX_URL`, `WATSONX_MODEL_ID`.
- `.env.exemple` updated with all new variables.
- `Base.metadata.create_all` picks up the new model automatically.

**Todo List:**
1. Create `backend/app/ai/__init__.py` (empty).
2. Create `backend/app/ai/provider.py` — `AbstractProvider`, `WatsonxProvider`, `MockProvider`.
3. Create `backend/app/ai/schemas.py` — `ReasonCode` enum, `AgentInput`, `RecommendedSlot`, `PlannerRecommendation`.
4. Create `backend/app/models/ai_recommendation.py` — `AIRecommendation` ORM model.
5. Add `AIRecommendation` import to `backend/app/models/__init__.py`.
6. Add new AI variables to `backend/app/core/settings.py`.
7. Update `.env.exemple` with placeholders for new variables.
8. Verify `Base.metadata.create_all` includes the new table (smoke test).

**Relevant Context:**
- `backend/app/models/__init__.py` — add import so Base sees new model at startup.
- `backend/app/core/settings.py` — existing `Settings(BaseSettings)` pattern.
- `backend/app/database.py` — `Base`, `engine`, `SessionLocal`.
- Provider abstraction uses `ABC` from stdlib — no new dependencies for the interface itself.
- `WatsonxProvider` will import `ibm-watsonx-ai`; this import should be lazy (inside the method body or guarded) so tests that use `MockProvider` do not require the SDK installed.
- `ibm-watsonx-ai` must be added to `requirements.txt` in ST-7.

---

### ST-7 — Planner Agent

**Status:** [ ] pending

**Intent:**
Implement the `PlannerAgent` class that constructs the prompt, calls the provider,
validates the structured response, enforces the candidate-list guard, and activates
fallback when needed.

**Expected Outcomes:**
- `backend/app/ai/agent.py` contains `PlannerAgent` class.
- `PlannerAgent.recommend(agent_input: AgentInput) -> PlannerRecommendation` works correctly.
- The prompt instructs the model to return only the JSON object — no surrounding prose.
- JSON parse failure triggers fallback, never a 500.
- Recommended slot not in candidate list triggers fallback, never a 500.
- Provider network failure triggers fallback, never a 500.
- `fallback_used` is `True` when any fallback path is taken.
- `ibm-watsonx-ai` added to `requirements.txt`.

**Todo List:**
1. Create `backend/app/ai/agent.py` — `PlannerAgent` class.
2. Implement `_build_prompt(agent_input: AgentInput) -> str`.
3. Implement `_parse_response(raw: str, candidates: list) -> PlannerRecommendation`.
4. Implement `_fallback(candidates: list, reason: str) -> PlannerRecommendation`.
5. Implement `recommend(agent_input: AgentInput) -> PlannerRecommendation`.
6. Add `ibm-watsonx-ai` to `backend/requirements.txt`.

**Relevant Context:**
- `backend/app/ai/provider.py` — `AbstractProvider` interface.
- `backend/app/ai/schemas.py` — `AgentInput`, `PlannerRecommendation`, `ReasonCode`.
- Prompt must be minimal and directive: instruct the model to return only a JSON object
  matching the output schema, using only slots from the candidate list.
- The prompt must include the task fields (title, priority, deadline, duration) and the
  candidate slots as a numbered list with ISO 8601 datetimes.
- Do not include user PII, internal IDs beyond task_id, or raw DB fields.

---

### ST-8 — Planner Service and Router

**Status:** [ ] pending

**Intent:**
Wire the Planner Agent to the HTTP layer. The service orchestrates the call to the
deterministic engine, the agent, and the audit persistence. The router exposes two
endpoints: recommend and decision.

**Expected Outcomes:**
- `backend/app/services/planner.py` contains `get_recommendation(task_id, from_date, db, provider)`.
- `backend/app/routers/planner.py` registers two endpoints under `/api/v1/planner`.
- `backend/app/main.py` registers the planner router.
- `backend/app/schemas/planner.py` contains `RecommendRequest`, `RecommendResponse`, `DecisionRequest`, `DecisionResponse`.
- `POST /planner/recommend` returns `RecommendResponse` with all required fields.
- `POST /planner/decision` records the user action and returns `DecisionResponse`.
- Provider is injected via FastAPI `Depends` — the router never instantiates `WatsonxProvider` directly.

**Todo List:**
1. Create `backend/app/schemas/planner.py` — `RecommendRequest`, `RecommendResponse`, `DecisionRequest`, `DecisionResponse`.
2. Create `backend/app/services/planner.py` — `get_recommendation` orchestration function.
3. Create `backend/app/routers/planner.py` — `POST /planner/recommend`, `POST /planner/decision`.
4. Create `get_provider()` FastAPI dependency in `backend/app/ai/provider.py` — reads `settings.AI_PROVIDER`, returns correct `AbstractProvider` instance.
5. Register planner router in `backend/app/main.py`.

**Service flow for `get_recommendation`:**
1. Load Task (404 if missing, 409 if not pending).
2. Call `suggest_slots(...)` — reuses existing engine service directly (no HTTP round-trip).
3. If candidate list is empty: raise 422 `"no candidate slots available"`.
4. Build `AgentInput`.
5. Call `PlannerAgent(provider).recommend(agent_input)`.
6. Persist `AIRecommendation` row to DB.
7. Return `RecommendResponse`.

**Relevant Context:**
- `backend/app/services/engine.py` — `suggest_slots` (reuse directly, no HTTP round-trip).
- `backend/app/routers/engine.py` — reference pattern for router structure, USER_ID, LOOKAHEAD_DAYS.
- `backend/app/models/ai_recommendation.py` (ST-6) — ORM model for persistence.
- `backend/app/ai/agent.py` (ST-7) — `PlannerAgent`.
- `backend/app/core/settings.py` (ST-6) — `AI_PROVIDER` setting.
- The service must call `suggest_slots` by loading blocks and slots from DB itself
  (same approach as the engine router). Do not make an internal HTTP call.

---

### ST-9 — Unit Tests for Planner Agent

**Status:** [ ] pending

**Intent:**
Test the `PlannerAgent` in full isolation using `MockProvider`. No database,
no real model, no watsonx credentials required. Validate all paths including happy path,
parse failure, invalid slot selection, and provider error.

**Expected Outcomes:**
- `backend/tests/test_planner_agent.py` passes with `pytest`.
- No real provider credentials needed.
- All fallback paths covered.
- Existing 114 tests continue to pass.

**Test cases:**

| Test | Scenario |
|---|---|
| `test_recommend_happy_path` | Mock returns valid JSON with candidate slot → PlannerRecommendation matches |
| `test_recommend_reason_codes_populated` | Returned reason_codes are a subset of ReasonCode enum |
| `test_recommend_slot_guard_triggers_fallback` | Mock returns a slot not in candidate list → fallback, fallback_used=True |
| `test_recommend_invalid_json_triggers_fallback` | Mock returns `"not json"` → fallback, fallback_used=True |
| `test_recommend_provider_exception_triggers_fallback` | MockProvider raises Exception → fallback, fallback_used=True |
| `test_recommend_single_candidate_only_slot_code` | One candidate → reason includes ONLY_SLOT_AVAILABLE |
| `test_recommend_fallback_selects_first_candidate` | Fallback always picks candidates[0] |
| `test_recommend_fallback_reason_code` | Fallback always includes PROVIDER_FALLBACK in reason_codes |
| `test_recommend_explanation_is_string` | explanation field is a non-empty string |

**Relevant Context:**
- `backend/app/ai/agent.py` — `PlannerAgent` under test.
- `backend/app/ai/provider.py` — `MockProvider`.
- `backend/app/ai/schemas.py` — `AgentInput`, `PlannerRecommendation`, `ReasonCode`.
- No DB fixture needed — `AgentInput` is built from plain Python objects.

---

### ST-10 — Integration Tests for Planner Router

**Status:** [ ] pending

**Intent:**
Test the planner endpoints end-to-end through TestClient using the in-memory SQLite
database and a `MockProvider` injected via dependency override. Validate HTTP contracts,
audit persistence, and decision recording.

**Expected Outcomes:**
- `backend/tests/test_planner_router.py` passes with `pytest`.
- MockProvider dependency override works cleanly without importing watsonx.
- `ai_recommendations` table row created on each recommend call.
- Decision endpoint updates the row correctly.
- Existing 114 tests continue to pass.

**Test cases:**

| Test | Expected HTTP | Scenario |
|---|---|---|
| `test_recommend_task_not_found` | 404 | task_id does not exist |
| `test_recommend_task_not_pending` | 409 | task already scheduled |
| `test_recommend_no_slots_available` | 422 | no candidate slots from engine |
| `test_recommend_success` | 200 | valid task, slots available, recommendation returned |
| `test_recommend_persists_audit_row` | 200 | ai_recommendations row created with correct task_id |
| `test_recommend_fallback_on_bad_provider` | 200 | MockProvider returns bad JSON → fallback, fallback_used=True in response |
| `test_decision_not_found` | 404 | recommendation_id does not exist |
| `test_decision_already_recorded` | 409 | calling decision twice for same recommendation |
| `test_decision_approved` | 200 | APPROVED action recorded |
| `test_decision_modified_valid_slot` | 200 | MODIFIED with a slot from the candidate list recorded |
| `test_decision_modified_invalid_slot` | 422 | MODIFIED with a slot NOT in the candidate list rejected |
| `test_decision_rejected` | 200 | REJECTED recorded, no final_slot required |
| `test_decision_approved_missing_final_slot` | 422 | APPROVED but final_start missing |

**Relevant Context:**
- `backend/tests/conftest.py` — `client`, `db_session` fixtures.
- Override `get_provider` FastAPI dependency with `MockProvider` for all planner tests.
- `backend/app/models/ai_recommendation.py` — query audit row after recommend call.

---

## Files to Create or Modify

```
backend/requirements.txt                          (modified — add ibm-watsonx-ai)
backend/app/core/settings.py                     (modified — add AI env vars)
backend/app/models/__init__.py                   (modified — import AIRecommendation)
backend/app/main.py                              (modified — register planner router)
.env.exemple                                     (modified — add AI variable placeholders)

backend/app/ai/__init__.py                       (new — empty)
backend/app/ai/provider.py                       (new — AbstractProvider, WatsonxProvider, MockProvider, get_provider dependency)
backend/app/ai/schemas.py                        (new — ReasonCode, AgentInput, PlannerRecommendation)
backend/app/ai/agent.py                          (new — PlannerAgent)

backend/app/models/ai_recommendation.py          (new — AIRecommendation ORM model)
backend/app/schemas/planner.py                   (new — RecommendRequest/Response, DecisionRequest/Response)
backend/app/services/planner.py                  (new — get_recommendation orchestration)
backend/app/routers/planner.py                   (new — POST /planner/recommend, POST /planner/decision)

backend/tests/test_planner_agent.py              (new — unit tests, no DB)
backend/tests/test_planner_router.py             (new — integration tests via TestClient)
```

No existing models, existing schemas, or existing engine/CRUD code is modified
beyond the four files listed above.

---

## Security and Risk Register

| Risk | Description | Mitigation |
|---|---|---|
| Prompt injection | User-controlled fields (task title) injected into the prompt | Sanitize or escape user content before insertion; treat title as data, not instructions |
| Raw model output leaked | Model returns harmful or verbose text | Agent always parses JSON; only structured fields are returned to client; raw completion is never stored or forwarded |
| Invalid slot returned by model | Model invents a datetime not in candidates | Slot guard: `recommended_slot` must match a candidate by exact `start_datetime`; fallback otherwise |
| Provider credentials in code | Hardcoded API keys | All credentials via environment variables; never committed; documented in `.env.exemple` |
| SDK import in tests | `ibm-watsonx-ai` required even when MockProvider is used | Lazy import inside `WatsonxProvider.complete()` — SDK not imported at module level |
| Audit row created before provider call | DB write then provider fail could leave orphaned rows | Persist audit row AFTER agent returns (either real or fallback recommendation); single write point |
| Decision recorded twice | Concurrent or duplicate POST /planner/decision | DB-level: `user_action` NOT NULL unique-per-row; application-level: 409 if `user_action` already set |

## Overengineering Risks

| Risk | Why tempting | Mitigation |
|---|---|---|
| Abstract repository for ai_recommendations | Testability | SQLAlchemy session passed directly; same pattern as Week 1 |
| Streaming completions | Lower latency | Not needed for planning use case; adds complexity |
| Async provider calls | FastAPI async | Deterministic engine is sync; keeping consistent avoids mixed async/sync complexity |
| Multiple model parameters | Fine-tuning the prompt | Start with defaults (temperature=0 for determinism); expose as env vars only if needed |
| Custom exception hierarchy | Robustness | Use FastAPI `HTTPException` as in Week 1; only `ProviderError` as an internal signal |
| Caching suggestions | Performance | No caching for MVP; suggestions are always fresh from the engine |
| Generic AI decision framework | Future-proofing | One PlannerAgent, one endpoint; generalize only when a second agent is approved |
