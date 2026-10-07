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
| Deterministic time/window hardening | Complete | Shared clock, future-only suggestions, daily booking window and deterministic tests |
| Deterministic reason-code governance | Complete | Two-field model output; backend-derived reason codes; candidate and fallback guards preserved |
| Frontend MVP | Complete | Tasks, commitments, planner decisions and explicit booking in one page; build/lint and real manual flow validated |

Historical plans use differing stage numbering in places. Their unchecked boxes and proposed contracts are not the current specification.

Latest isolated automated suite after deterministic reason-code governance: **216 passed, 1 skipped, 0 failed** (2 existing warnings). The only skip is the credential-gated watsonx smoke with credentials disabled. This run used the actual local source mounted read-only, not a stale container copy. The separate real smoke previously passed; it was not rerun for this change.

The current MVP is **feature-frozen**. Completed architecture decisions remain closed; the priorities below concern presentation, deployment and usage.

The frontend MVP now integrates the validated backend flow in one page. No authentication or deployed production environment exists. Frontend build and lint passed without warnings; manual real recommendation/decision/booking validation passed. This is an MVP, not a production design.

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
- AI never creates or modifies scheduling boundaries. The model selects `recommended_candidate_id` only. PlannerAgent resolves datetimes from the original input candidate list.
- The model returns only recommended_candidate_id and explanation. Backend code derives reason_codes; model-supplied codes have no authority.
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

## Frontend MVP Architecture and API Rules

The one-page React + TypeScript + Vite MVP is complete:
- App owns task/commitment lists, refresh state and selected task.
- TasksPanel creates/lists tasks and displays title, duration, priority, deadline and status. Only pending tasks can be planned.
- FixedBlocksPanel creates/lists weekly or once commitments. Monday=0 through Sunday=6. Overnight end times are allowed; spans_next_day is never sent and the returned overnight flag is shown.
- PlannerPanel requests recommendations and displays the recommended slot, explanation, reason_codes, fallback_used and all original candidates.
- api/types.ts mirrors HTTP request/response types; api/client.ts uses fetch only, with backend error details and no automatic POST retries.
- utils/format.ts formats dates for display only. Styling is plain responsive CSS with accessible labels, loading states and visible errors.

No router, state-management library, UI framework, charts, authentication or new frontend dependencies were added.

Vite development proxy: /api → http://localhost:8000. The frontend uses relative API URLs; no backend CORS changes were needed. This is a local development setup, not a production hosting solution.

| Method | Endpoint | Frontend action |
|---|---|---|
| GET / POST | /api/v1/tasks/ | List / create tasks |
| GET / POST | /api/v1/blocks/ | List / create commitments |
| POST | /api/v1/planner/recommend | Obtain a complete recommendation snapshot |
| POST | /api/v1/planner/decision | Record APPROVED, MODIFIED or REJECTED |
| POST | /api/v1/engine/book | Explicit booking after a recorded decision |

Keep these interaction rules:
- Retain the complete RecommendResponse. MODIFIED selects only from that exact candidate_slots array; never regenerate it with engine/suggest.
- APPROVED sends recommendation_id/action only; the backend uses the persisted recommended slot.
- MODIFIED sends the selected original start/end strings. REJECTED sends recommendation_id/action and never exposes a Book button.
- After APPROVED/MODIFIED succeeds, show “Decision recorded. Task is still pending.” Book is a separate explicit click.
- Book sends task_id from the recommendation and start_datetime from decision.final_start. Confirmation displays the returned ScheduledSlot, then refreshes Tasks.
- Preserve original backend datetime strings in payloads. Never use toISOString() or convert naive datetimes to UTC; formatting is display-only.
- Preserve recommendation/decision state on failed booking; show 422/404/409 backend messages.
- Busy flags and submission refs block repeated clicks. Successful decisions disable further decisions on that snapshot.
- App keys PlannerPanel by selected task; unmounted panels ignore stale responses. Booking completion still refreshes Tasks after a task switch.
- A page reload discards the local planner flow. There is no recommendation-recovery endpoint or browser persistence.
- Do not put watsonx credentials in browser configuration or frontend bundles.

Historical validated frontend flow, before final reason-code governance: Task 8 → recommendation 3 (fallback_used=false) → MODIFIED to an original candidate → pending with zero slots → explicit booking → ScheduledSlot 2 → scheduled. Selected slot: 2026-10-07 14:00–14:30, preserved as backend naive datetime strings. REJECTED and once overnight creation were also confirmed.

Validation uses npm run build, npm run lint and manual end-to-end checks. Both commands passed with no warnings. There is no automated frontend interaction test runner; adding one requires separate scope.

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
  "explanation": "This valid candidate offers an early start for a high-priority task."
}
```

PlannerAgent owns fence removal, json.loads, Pydantic structural validation, strict integer candidate-ID validation, bounds checks, deterministic candidate lookup and reason-code derivation. Stored explanations are limited to 200 characters. Extra model fields are ignored; they cannot override derived reason codes.

| Code | Deterministic rule |
|---|---|
| HIGH_PRIORITY | task.priority == "high" |
| MEDIUM_PRIORITY | task.priority == "medium" |
| LOW_PRIORITY | task.priority == "low" |
| EARLIEST_SLOT | selected candidate_id == 0 |
| ONLY_SLOT_AVAILABLE | len(candidate_slots) == 1 |
| DEADLINE_CLOSE | deadline exists and (deadline - selected_candidate.date).days <= 1 |
| PROVIDER_FALLBACK | System-only fallback path |

Multiple factual codes can apply together. DEADLINE_CLOSE uses calendar-date subtraction against the selected candidate, not current time or a rolling 48-hour window. MOST_BUFFER_BEFORE_DEADLINE has been removed from the final vocabulary. Historical audit rows are not rewritten.

Fallback is limited to ProviderError, malformed JSON, structurally invalid output (including missing fields), or invalid candidate_id (including negative/out-of-range IDs). It selects candidate 0, sets fallback_used=true, and returns only PROVIDER_FALLBACK plus the existing concise default explanation. Extra model reason_codes do not trigger fallback. Empty candidates yield route HTTP 422 before a provider call or audit insert.

AI may compare valid options and supply a concise explanation; it never creates availability, mutates Task.status or books. Reason-code semantics are now deterministic, while free-text explanation accuracy is not guaranteed. No learned-feedback pipeline exists.

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
- one user message containing the current PlannerAgent prompt;
- temperature=0, max_tokens=512;
- response_format={"type":"json_object"};
- returns choices[0].message.content as a string only.

Transport shape errors and upstream failures become ProviderError. JSON parsing and domain validation must remain in PlannerAgent.

Unknown AI_PROVIDER raises ConfigurationError when the dependency is resolved. Despite a provider docstring saying “startup,” lifespan does not currently validate it.

Real IBM Cloud authentication, watsonx project/Runtime and smoke test are validated. SDK tested: 1.8.0. Validated runtime model: meta-llama/llama-3-3-70b-instruct. The code's default model setting remains granite-4-1-8b; distinguish defaults from the actual validated environment.

The available Lite/Sydney runtime did not support the planned Granite model. A non-IBM model is currently used through IBM watsonx. Future Granite validation may require a supported region/runtime/deployment; do not silently change provider or force broad workarounds.

The deprecated text-generation transport was replaced by chat with accepted JSON response format. The /ml/v1/text/generation deprecation warning disappeared. Controlled reliability: before 2/5 valid, 3/5 malformed-JSON fallbacks; after 5/5 valid, 0/5 fallbacks. This historical comparison preceded deterministic reason-code governance and does not establish production reliability. No new live five-call evaluation was run for the final two-field contract.

The real persisted end-to-end flow was validated using the earlier fallback recommendation: approval left Task pending and no slot existed until explicit engine/book created it and set scheduled. The later five-call chat comparison did not create bookings or audit rows. A subsequent frontend-backed real chat flow did persist recommendation 3 without fallback, record MODIFIED, and create ScheduledSlot 2 only after explicit booking.

## Testing Rules

Automated tests must not connect to development MySQL:
- SQLite in memory, StaticPool, check_same_thread=False;
- foreign_keys enabled;
- get_db dependency override;
- application engine patched so lifespan table creation is isolated.

Mock external AI calls. Unit/integration tests require no real credentials. Only the explicitly credential-gated watsonx smoke test may make a live call; it asserts nonempty string connectivity, not PlannerAgent JSON correctness, and does not print raw output.

Preserve coverage for parsing/schema/strict candidate bounds/fallback and deterministic reason-code derivation, injected-provider audit metadata, from_date, human decision semantics and deterministic booking conflicts. Chat transport tests verify parameters, text passthrough, malformed response shapes and upstream errors. Do not reduce coverage or make tests depend on model-specific prose.

Latest validation ran against a read-only bind mount of the actual local backend source, with AI_PROVIDER=mock and WATSONX_API_KEY disabled; SQLite overrides isolated the database. Result: **216 passed, 1 skipped, 0 failed**, 2 warnings. Bob's earlier stale-container test report is not validation evidence. See deterministic-reason-codes-plan.md for the recorded command and coverage.

The former clock-dependent booking test now uses a fixed clock with no time-of-day skip. Engine/planner router and BookRequest time tests use fixed timestamps; pure service tests receive explicit now. The only skip is the live smoke without credentials. The earlier live smoke and real frontend flow were not rerun for governance or this documentation update.

Never print credentials, dump environment files, commit secrets or persist raw completions. Dependencies are currently unpinned; SDK 1.8.0 is the tested version, not a requirements pin.

## Known Technical Debt and Limits

1. Resolved: deadline booking test uses a fixed clock and isolates deadline failure from work-window failure; the time-of-day skip is removed.
2. SQLAlchemy nullable date annotation deprecation warning in models/fixed_block.py.
3. utcnow-based engine/planner helpers were replaced with fixed-clock timestamps. No utcnow warnings occurred in the latest Python 3.12 suite; unrelated helpers elsewhere remain outside this scope.
4. Resolved: reason-code semantic consistency is backend-derived. Free-text explanations remain model-generated and can still be inaccurate.
5. Validated model is non-IBM because of Lite/Sydney Granite availability.
6. Future Granite testing needs a supported runtime/region/deployment.
7. Five post-chat successes are a small sample, not a guarantee.
8. Resolved: booking work-window and same-day elapsed-candidate gaps, with boundary, cutoff and nonmutation regression tests.
9. Existing Starlette/httpx and third-party model license warnings remain; chat removed only the text-generation deprecation warning.
10. Timezone-aware scheduling is not implemented: naive local datetimes are intentionally preserved end-to-end.
11. Frontend has no automated interaction test runner yet and remains an MVP rather than a production design.

Do not opportunistically clean up warnings or expand architecture. Address them only when functionally necessary or through approved dedicated work.

## Current Next Priorities

1. Visual polish.
2. Deployment.
3. Screenshots/GIF/demo evidence.
4. Presentation/LinkedIn.
5. Optional real-world usage.

These are priorities for separately scoped work, not authorization to add backend features. Keep the current MVP feature-frozen. No Auditor Agent, new provider or reopening of completed architecture decisions is planned. Known limitations remain documented rather than becoming an automatic feature backlog.

## Before Changing Code

For each major sub-task:
1. Respect the current feature freeze; require explicit scope for any change. Read AGENTS.md and the current relevant plan/validation record.
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
- broad production UI redesign or new product features; deployment is a current priority but requires its own approved scope;
- additional AI providers, including Gemini;
- autonomous booking without human confirmation;
- Auditor Agent or other new agents/features.

Those belong to later phases or separate approved scope. Never silently change the approved architecture.
