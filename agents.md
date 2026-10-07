# LifeOps Project Context

Operational context for IBM Bob, Codex, Claude Code, and future coding agents. Updated 2026-10-07. Read this document and the relevant current implementation before changing code.

## Project Goal

LifeOps is an auditable decision-support application for organizing personal tasks around university, work, travel, and other fixed commitments.

The two layers are intentionally separate:
1. deterministic scheduling and business constraints;
2. AI recommendation, explanation, and human decision recording.

Deterministic rules have priority. AI must never override hard scheduling constraints. Keep the architecture simple, readable, and within approved scope; prefer pure deterministic functions and avoid unnecessary frameworks, abstractions, or microservices.

## Current Status

| Milestone | Status | Implemented scope |
|---|---|---|
| ST-1 | Complete | React/TypeScript/Vite scaffold, FastAPI, health endpoint, Docker networking and MySQL healthcheck |
| ST-2 | Complete | SQLAlchemy domain models, recurrence, overnight blocks, constraints, indexes and FK cascade |
| ST-3 | Complete | Pydantic create/update/read schemas and request-local validation |
| ST-4 | Complete | CRUD, merged PATCH validation, derived fields, consistent errors and atomic slot deletion/status reset |
| ST-5 | Complete | Pure deterministic engine, suggestions and explicit booking with current-state revalidation |
| ST-6 | Complete | AI foundation, structured schemas, provider abstraction and AIRecommendation audit model |
| ST-7 | Complete | PlannerAgent, candidate selection, output guards and deterministic fallback |
| ST-8 | Complete | Planner service and recommend/decision routes with audit persistence |
| ST-8 cleanup | Complete | Candidate-ID contract, injected-provider audit metadata, planner from_date validation and regression coverage |
| ST-9 | Complete | AI test coverage and real watsonx validation; credential-gated smoke test and chat migration validated |

Historical plans use differing stage numbering in places. Their unchecked boxes and proposed contracts are not the current specification.

Latest isolated automated suite after deterministic gap fixes: **186 passed, 1 skipped, 0 failed** (2 existing warnings). Real credential-gated smoke test run separately: **1 passed**. These are recorded validation results, not a guarantee of a fresh run.

The frontend is still the stock scaffold, not an integrated scheduling/planner UI. No authentication or deployed production environment exists. The backend API flow is validated.

## Approved Stack and Repository Map

- Frontend: React, TypeScript, Vite.
- Backend: Python, FastAPI, Pydantic, SQLAlchemy.
- Development database: MySQL 8, Docker Compose.
- Tests: pytest, FastAPI TestClient, isolated SQLite in memory.
- AI: IBM watsonx via ibm-watsonx-ai; MockProvider for deterministic tests.
- Development: IBM Bob with human review; Codex and other tools may assist.
- Planned deployment only: Vercel, Azure App Service, Azure Database for MySQL.

Relevant backend directories under `backend/app/`:
- `models/`: persisted domain and audit records.
- `schemas/`: HTTP contracts.
- `services/engine.py`: pure availability calculations.
- `services/planner.py`: recommendation and human-decision application rules.
- `routers/`: database loading, HTTP orchestration, explicit booking.
- `ai/agent.py`, `ai/schemas.py`, `ai/provider.py`: prompt, model-output guards and provider transport.
- `core/settings.py`: environment-backed configuration.

`backend/tests/` contains isolated engine, CRUD, AI, router and mocked chat tests plus the credential-gated live smoke test. Docker Compose runs MySQL and API, not the frontend. Application lifespan currently creates tables through SQLAlchemy metadata; do not invent a migration framework.

## Do Not Regress These Decisions

- The deterministic engine owns scheduling validity and remains independent from AI.
- AI receives only deterministic candidates; it never creates availability or invents datetimes.
- The model selects `recommended_candidate_id` only. PlannerAgent resolves datetimes from the original input candidate list.
- Recommend → decision → engine/book are three separate actions.
- `/planner/decision` never creates a ScheduledSlot or mutates Task.status.
- APPROVED ignores chosen_start/chosen_end and uses the persisted recommended slot.
- MODIFIED requires an exact slot from the original persisted candidate list, not a refreshed engine response.
- REJECTED has no final selected slot and books nothing.
- `/engine/book` must revalidate current state; an earlier candidate or approval is not proof of current availability.
- ScheduledSlot creation and Task.status update are one atomic commit.
- Audit provider/model metadata comes from the actually injected provider instance.
- Raw completions, credentials and hidden chain-of-thought are not persisted.
- Model/provider failures preserve the deterministic fallback.
- Invalid provider configuration fails explicitly; it must not silently select MockProvider.
- Pydantic handles request-local rules; merged-state domain rules belong in the application layer.
- Derived fields are computed server-side; tests must not use development MySQL.

## Domain Rules

### User

No authentication yet. Temporary user_id = 1. Do not imply tenant isolation or production access control.

### FixedBlock

Unavailable time supports `weekly` and `once` recurrence:
- weekly requires weekday 0–6 and forbids date;
- once requires date and forbids weekday;
- equal start_time/end_time is invalid;
- crossing midnight is allowed;
- spans_next_day is computed as end_time < start_time.

PATCH must combine stored fields with incoming fields before recurrence validation and derived-field calculation. Do not mutate the row before validating the merged state. Overnight occupancy includes the following day and previous-day tails when examining a date.

### Task

- duration_minutes > 0.
- Priority: low, medium or high; default medium.
- Deadline is optional. Newly assigned deadlines cannot be in the past.
- Existing tasks may naturally become overdue; unrelated PATCH operations must not reject them.
- New tasks start pending; create/update schemas do not expose status.
- Status enum: pending, scheduled, done. A done-transition endpoint is not implemented.

### ScheduledSlot

- At most one per Task, enforced by a unique task_id constraint.
- Generic creation is not exposed; creation occurs through POST /api/v1/engine/book.
- End is computed from start plus stored task duration.
- Deletion resets the task to pending and deletes the slot atomically.
- Relevant task foreign keys use cascade deletion.

## Deterministic Engine Rules

GET /api/v1/engine/suggest loads a pending Task and current commitments/slots. Optional from_date defaults to today; past dates are rejected. Default lookahead is seven days; at most ten candidates are returned in ascending start order.

The pure service normalizes occupied intervals, includes overnight blocks and previous-day tails, merges overlapping and adjacent intervals, computes free intervals within configured working hours, and emits duration-sized slots. Intervals use [start, end), so touching boundaries are not conflicts.

Work-window defaults are 08:00–22:00. Deadline enforcement is inclusive:
`end_datetime <= datetime.combine(task.deadline, WORK_END)`.
A candidate ending exactly at WORK_END on the deadline date is valid.

POST /api/v1/engine/book:
1. loads the Task and requires pending;
2. normalizes the requested start to a naive datetime and requires a future start;
3. computes end server-side and requires the entire interval within that date's configured work window;
4. validates the deadline ceiling;
5. checks current FixedBlocks, including overnight occupancy;
6. checks current ScheduledSlots;
7. creates a ScheduledSlot and sets status scheduled in one commit.

Do not trust a previous suggestion. The book endpoint accepts task_id/start_datetime; it does not require recommendation_id or an approval audit row. Human approval is an explicit workflow step, not a server-enforced linkage between these endpoints.

Implemented deterministic safeguards:
- core/clock.py exposes now(), returning naive local time. Each scheduling HTTP handler captures it once and derives today from that same value.
- suggest_slots requires explicit now and excludes starts at or before it before counting results. Existing interval generation and slot alignment remain unchanged; following days continue normally.
- Booking requires window_start <= start < end <= window_end for the start date, rejecting out-of-hours and cross-midnight bookings with 422 before mutation.

Remaining limitation:
- Datetimes are currently naive; stripping tzinfo is not timezone conversion. Do not imply comprehensive timezone support.

## PlannerAgent Contract and Fallback

POST /api/v1/planner/recommend accepts task_id and optional from_date. It loads a pending task and obtains candidates through the deterministic service, not an HTTP round trip. Past from_date is rejected just as in engine/suggest.

The prompt contains task title, duration, priority, deadline and indexed deterministic candidates. Model output contract:

```json
{
  "recommended_candidate_id": 0,
  "reason_codes": ["HIGH_PRIORITY", "EARLIEST_SLOT"],
  "explanation": "This valid candidate offers an early start for a high-priority task."
}
```

This example documents the contract; it does not mean the production prompt was rewritten during chat migration.

PlannerAgent owns fence removal, json.loads, Pydantic validation, candidate bounds, reason-code validation and candidate lookup. It limits the stored explanation to 200 characters.

Allowed reason codes:
- DEADLINE_CLOSE
- HIGH_PRIORITY
- MEDIUM_PRIORITY
- EARLIEST_SLOT
- MOST_BUFFER_BEFORE_DEADLINE
- ONLY_SLOT_AVAILABLE
- PROVIDER_FALLBACK — reserved for system fallback; model output using it is rejected.

AI may rank or compare valid options and explain priority/deadline considerations. It must not bypass commitments, invent availability, mutate Task.status or book. Feedback is recorded for audit; no learned-feedback pipeline is implemented.

Malformed JSON, invalid schema/candidate/reason codes or ProviderError selects the first deterministic candidate, sets fallback_used=true and uses PROVIDER_FALLBACK with a concise default explanation. A fallback still has a valid recommended slot. Empty candidates cannot produce a recommendation: the route returns 422.

Reason-code membership is validated, semantic truth is not. A valid structured response can still use EARLIEST_SLOT inaccurately for a later candidate.

## HTTP and Human Decision Rules

All application routes use /api/v1.
- POST /planner/recommend: HTTP 201, including deterministic fallback. Returns recommendation_id, task_id, recommended_slot, reason_codes, explanation, original candidate_slots and fallback_used.
- POST /planner/decision: HTTP 200, records APPROVED/MODIFIED/REJECTED only.
- POST /engine/book: HTTP 201 after explicit booking and current-state validation.
- GET /health: basic application health response.

APPROVED uses stored recommended_start/end even when chosen fields are provided. MODIFIED requires both chosen fields to exactly match a stored candidate after current naive datetime normalization. REJECTED leaves final_start/final_end null. A repeated decision returns 409. Multiple recommendations for a pending task are allowed; do not invent database uniqueness for decisions.

Use standard FastAPI errors: 404 missing resource, 409 state/conflict, 422 invalid business input. No custom exception framework is needed.

## Auditability

Each successful recommend request persists AIRecommendation with:
- id, created_at, task_id, user_id;
- provider and model_id from the injected instance;
- original full candidate_slots_json;
- recommended_start/end, reason_codes, concise explanation and fallback_used;
- user_action and final_start/end populated by the later decision.

The original list is immutable decision context for MODIFIED validation. Final fields record the human decision, not proof of booking. Do not store raw model output, hidden reasoning or secrets. Do not reconstruct provider metadata from settings when a different instance was injected.

## Provider Rules and Real watsonx State

AbstractProvider.complete(prompt) -> str remains the interface. provider_name and model_id are read-only audit metadata. MockProvider returns its configured string; default mock dependency returns "{}" and therefore uses PlannerAgent fallback. It is not a production AI substitute.

WatsonxProvider imports the SDK lazily and obtains credentials/configuration from environment-backed settings. Current transport:
- ModelInference.chat();
- one user message containing the unchanged PlannerAgent prompt;
- temperature=0, max_tokens=512;
- response_format={"type":"json_object"};
- returns choices[0].message.content as a string only.

Transport shape errors and upstream failures become ProviderError. JSON parsing and domain validation must remain in PlannerAgent.

Unknown AI_PROVIDER raises ConfigurationError when the dependency is resolved. Despite a provider docstring saying “startup,” lifespan does not currently validate it.

Real IBM Cloud authentication, watsonx project/Runtime and smoke test are validated. SDK tested: 1.8.0. Validated runtime model: meta-llama/llama-3-3-70b-instruct. The code's default model setting remains granite-4-1-8b; distinguish defaults from the actual validated environment.

The available Lite/Sydney runtime did not support the planned Granite model. A non-IBM model is currently used through IBM watsonx. Future Granite validation may require a supported region/runtime/deployment; do not silently change provider or force broad workarounds.

The deprecated text-generation transport was replaced by chat with accepted JSON response format. The /ml/v1/text/generation deprecation warning disappeared. Controlled reliability: before 2/5 valid, 3/5 malformed-JSON fallbacks; after 5/5 valid, 0/5 fallbacks. This small sample does not establish production reliability.

The real persisted end-to-end flow was validated using the earlier fallback recommendation: approval left Task pending and no slot existed until explicit engine/book created it and set scheduled. The later five-call chat comparison did not create bookings or audit rows.

## Testing Rules

Automated tests must not connect to development MySQL:
- SQLite in memory, StaticPool, check_same_thread=False;
- foreign_keys enabled;
- get_db dependency override;
- application engine patched so lifespan table creation is isolated.

Mock external AI calls. Unit/integration tests require no real credentials. Only the explicitly credential-gated watsonx smoke test may make a live call; it asserts nonempty string connectivity, not PlannerAgent JSON correctness, and does not print raw output.

Preserve coverage for parsing/schema/invalid codes/candidate bounds/fallback, injected-provider audit metadata, from_date, human decision semantics and deterministic booking conflicts. Chat transport tests verify parameters, text passthrough, malformed response shapes and upstream errors. Do not reduce coverage or make tests depend on model-specific prose.

Recorded validation commands, executed in the API container:
```text
docker compose exec -T -e WATSONX_API_KEY= api python -m pytest tests -q -p no:cacheprovider
docker compose exec -T api python -m pytest tests/test_watsonx_provider.py -v -p no:cacheprovider
```
The latest first-command run deliberately disabled live credentials: 186 passed, 1 skipped, 0 failed, with 2 warnings. Its only skip was the smoke test. The separate live smoke passed during prior watsonx validation; it was not rerun for deterministic fixes. The former clock-dependent booking test now runs with a fixed clock and has no time-of-day skip. Engine/planner router and BookRequest time tests use fixed timestamps; pure service tests pass explicit now.

Never print credentials, dump environment files, commit secrets or persist raw completions. Dependencies are currently unpinned; SDK 1.8.0 is the tested version, not a requirements pin.

## Known Technical Debt and Limits

1. Resolved: deadline booking test uses a fixed clock and isolates deadline failure from work-window failure; the time-of-day skip is removed.
2. SQLAlchemy nullable date annotation deprecation warning in models/fixed_block.py.
3. utcnow-based engine/planner helpers were replaced with fixed-clock timestamps. No utcnow warnings occurred in the latest Python 3.12 suite; unrelated helpers elsewhere remain outside this scope.
4. Reason-code semantic consistency is unchecked; later candidates received EARLIEST_SLOT.
5. Validated model is non-IBM because of Lite/Sydney Granite availability.
6. Future Granite testing needs a supported runtime/region/deployment.
7. Five post-chat successes are a small sample, not a guarantee.
8. Resolved: booking work-window and same-day elapsed-candidate gaps, with boundary, cutoff and nonmutation regression tests.
9. Existing Starlette/httpx and third-party model license warnings remain; chat removed only the text-generation deprecation warning.

Do not opportunistically clean up warnings or expand architecture. Address them only when functionally necessary or through approved dedicated work.

## Current Next Priorities

These are candidates for scoped human review, not authorization to implement:
- inspect reason-code semantic consistency without weakening candidate or fallback guards;
- broaden controlled reliability evaluation while protecting credentials and raw-output privacy;
- assess Granite on supported infrastructure;
- plan frontend API integration separately.

No Auditor Agent, new provider or new feature is part of the completed validation scope.

## Before Changing Code

For each major sub-task:
1. Read AGENTS.md and the current relevant plan/validation record.
2. Inspect the relevant implementation, tests and existing working-tree changes.
3. Distinguish historical proposals from implemented behavior; report contradictions.
4. Propose a bounded plan, identify files and affected business rules.
5. Identify required tests and credential/database boundaries.
6. Obtain human approval before an unapproved major scope; existing explicit authorization remains valid.
7. Implement only that scope and preserve the invariants above.
8. Run appropriate isolated tests; run live checks only when authorized.
9. Report results, warnings, limitations and files changed.
10. Update documentation; do not silently expand scope or commit unless requested.

Preferred Bob workflow: Plan → human review → Agent implementation → tests → validation → reviewed commit. Bob is not the only tool that may assist.

Read README for the external overview, watsonx-validation-plan.md for completed real validation, and BOB-DEVELOPMENT-LOG.md for chronology. lifeops-week1-plan.md, lifeops-week2-plan.md, lifeops-st*-plan.md and the pre-chat watsonx-e2e-validation-report.md retain historical proposals/results; their stale unchecked tasks, datetime-output examples and settings-derived audit suggestions must not override current contracts.

## Do Not Implement Yet

Without explicit approval, do not add:
- authentication or OAuth;
- Redis, Celery or background jobs;
- microservices, Kubernetes or OpenShift;
- production UI redesign or deployment;
- additional AI providers, including Gemini;
- autonomous booking without human confirmation;
- Auditor Agent or other new agents/features.

Those belong to later phases or separate approved scope. Never silently change the approved architecture.
