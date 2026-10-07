# LifeOps Development Log

This chronological record describes the development decisions and validations leading to the current state. Early milestones are ordered by development phase rather than assigned unverified dates. Latest validation: 2026-10-07.

## Planning and Human Review

IBM Bob supported planning and implementation across the SDLC, including architecture, testing, debugging and documentation. Plans were reviewed by a human before Bob Agent implementation. Human review remained part of the development process rather than delegating architectural authority to model output.

Bob was not the only tool used. Codex and other tools also assisted with validation, diagnosis and documentation. This log records technical outcomes without attributing all work to a single tool.

## Deterministic Foundation: ST-1 through ST-5

The project first established the React/TypeScript/Vite scaffold, FastAPI backend, Docker/MySQL setup, SQLAlchemy domain models, Pydantic contracts and CRUD application rules.

An important human-caught design decision was support for commitments crossing midnight. FixedBlocks use the server-derived spans_next_day flag rather than forbidding end_time < start_time. The engine includes overnight tails from the previous day when computing occupancy.

Request-local validation stayed in Pydantic. Rules requiring existing state were applied after merging PATCH input with stored records. ScheduledSlot uniqueness, FK cascade and atomic deletion/status reset were retained.

The deterministic engine was built before AI. It computes candidates from commitments, existing slots, working hours, duration and deadlines. Explicit booking rechecks current conflicts/deadlines before atomically creating a slot and marking the Task scheduled. AI was not used to decide hard scheduling validity.

## AI Foundation and PlannerAgent: ST-6 and ST-7

Only after hard-constraint scheduling existed were the provider abstraction, structured AI schemas, AIRecommendation audit model and PlannerAgent introduced.

The provider interface stayed complete(prompt) -> str. MockProvider supports isolated tests; WatsonxProvider handles real transport. PlannerAgent owns output parsing and validation.

The initial model-generated datetime contract was replaced with candidate_id selection. The model chooses an indexed deterministic candidate; application code resolves its start/end from the original list. This prevents model-invented datetimes from becoming recommendations.

At that stage, malformed output, invalid candidate IDs/reason codes and provider errors preserve a deterministic first-candidate fallback. Empty availability cannot be converted into invented slots.

## Planner Routes and Cleanup: ST-8

Recommendation persistence and human APPROVED/MODIFIED/REJECTED decisions were added as separate actions from booking.

APPROVED uses the stored recommendation and ignores optional chosen fields. MODIFIED accepts only a slot from the original stored candidate list. REJECTED does not book. Decision recording never mutates Task.status or creates ScheduledSlot.

Review corrected audit metadata to read provider_name/model_id from the actually injected provider instance, instead of reconstructing them from global settings. Regression tests protect dependency overrides and accurate attribution.

A planner from_date gap was discovered and fixed: planner recommendation now defaults to today and rejects past dates consistently with deterministic suggestions.

Audit records store original candidates, concise explanations, fallback status and human decisions. Raw completions and hidden chain-of-thought are excluded.

## Real watsonx Integration: ST-9

IBM watsonx project/Runtime setup and real IBM Cloud API authentication were validated. WatsonxProvider successfully called a real model, and a credential-gated smoke test passed.

The available Lite/Sydney runtime did not support the planned IBM Granite model. The validated runtime therefore used meta-llama/llama-3-3-70b-instruct through IBM watsonx. This limitation was documented rather than hiding it or adding another provider.

The first persisted real recommendation returned HTTP 201 with fallback_used=true. Its selected slot came from the deterministic candidate list, and its audit row retained correct watsonx/model metadata.

## Real Human-in-the-Loop Booking Validation

The existing recommendation_id=1 was approved without generating a replacement recommendation. Decision returned HTTP 200 with the persisted recommended start/end. Task 1 remained pending and no ScheduledSlot existed.

A later explicit POST /api/v1/engine/book returned HTTP 201, created ScheduledSlot 1 and changed Task 1 to scheduled. Booking revalidated current state and recomputed end. This confirmed that decision recording does not automatically book.

The validated slot was 2026-10-08 08:00–09:00. This pre-chat end-to-end run used deterministic fallback; it demonstrated action separation and safe recovery from model failure.

## Malformed JSON Diagnosis and Controlled Baseline

Subsequent real PlannerAgent checks diagnosed recurring malformed JSON. A controlled five-scenario sample produced two valid structured responses and three deterministic fallbacks.

The failures included unquoted reason-code tokens; one output also repeated objects/prose and ended incompletely, consistent with truncation. json.loads reported “Expecting value: line 3 column 20 (char 54)” for each failure. These were output-format failures rather than authentication failures.

Deterministic fallback preserved valid candidate selection. It did not confer semantic accuracy on the model or bypass booking validation. Raw responses were captured locally for diagnosis only, not in the audit database.

## Chat API and JSON Response Format

A narrow provider transport migration replaced deprecated text generation with ModelInference.chat(). SDK 1.8.0 and the current model accepted response_format={"type":"json_object"}, temperature=0 and max_tokens=512.

The provider continues returning only message text. PlannerAgent parsing, validation, candidate guards, metadata attribution and fallback behavior remained unchanged. No prompt change or new architecture was introduced.

The text-generation API deprecation warning disappeared. The same five-scenario comparison improved from **2/5 valid structured responses to 5/5**, with fallbacks falling from **3/5 to 0/5**. No new audit rows or bookings were created by these direct reliability calls.

This is a small sample, not a reliability guarantee. Valid JSON still contained questionable reason-code semantics, including EARLIEST_SLOT for a later candidate.

## Validated Snapshot After Chat Migration

ST-1 through ST-9 and ST-8 cleanup are complete. Recorded automated result: **160 passed, 1 skipped, 0 failed**; separate real smoke: **1 passed**. The automated run disabled credentials and skipped the live smoke. At that stage, a booking test was clock-dependent; the subsequent hardening below removed its skip.

At that stage the frontend was a scaffold. Deployment, authentication, additional agents/providers and autonomous booking have not been implemented.

Remaining debt includes nullable date and utcnow deprecations, clock-dependent tests, reason-code semantic consistency, Granite runtime availability and the small reliability sample. Repository inspection also identified booking-window and elapsed-suggestion gaps. These were subsequently fixed under explicit approval, as recorded below.

See agents.md for architecture invariants and operational rules, watsonx-validation-plan.md for validation evidence, and the historical watsonx-e2e-validation-report.md for the original endpoint record.

## Approved Deterministic Gap Fixes — 2026-10-07

Following inspection and human approval, the booking route now requires the complete task interval inside the configured work window on its start date. Invalid bookings return 422 before any status/slot mutation. Exact window boundaries remain valid; conflicts, deadline checks and the atomic transaction are unchanged.

A minimal core/clock.py now() helper returns naive local time. Scheduling handlers capture time once, derive today from it, and pass that value to the pure engine. suggest_slots excludes starts at or before the cutoff without counting them toward ten results, retaining existing slot alignment and searching later days.

Scheduling tests use fixed timestamps. The former deadline-booking skip is removed, with deadline behavior isolated from work-window validation. BookRequest keeps its existing temporal validation through the shared clock.

Full isolated suite with WATSONX_API_KEY disabled: **186 passed, 1 skipped, 0 failed**, 2 existing warnings (SQLAlchemy nullable date and Starlette/httpx). The only skip is the credential-gated smoke test. Documentation was updated only after the suite passed. No PlannerAgent, provider, model, database schema, endpoint contract, frontend or timezone architecture changes were made.
## Frontend MVP Planning and Implementation — 2026-10-07

A bounded frontend plan was reviewed and approved before implementation: one page with Tasks, Fixed commitments and Plan a task. The human explicitly deferred Vitest/React Testing Library and approved TypeScript build, lint and manual validation instead. Codex assisted with planning, frontend implementation, validation and documentation; this phase is not attributed solely to Bob.

The MVP uses React hooks, simple components, fetch and plain responsive CSS. It creates/lists tasks and commitments, supports weekly/once recurrence and overnight commitments, and displays the complete recommendation, explanation, reason codes, fallback flag and original candidates.

PlannerPanel retains the full recommendation snapshot. APPROVED uses the persisted recommendation; MODIFIED selects an original candidate only; REJECTED does not book. Backend datetime strings are preserved exactly. A recorded decision leaves the task pending, and a separate Book selected slot action uses decision.final_start.

The Vite /api → http://localhost:8000 proxy enabled local integration without backend CORS changes. No new frontend dependencies, backend changes, API changes, environment changes or test runner were introduced.

## Real Frontend Flow Validation — 2026-10-07

Recorded real flow: Task 8 → recommendation 3 → fallback_used=false → MODIFIED to original candidate 2026-10-07 14:00–14:30 → Task still pending, zero slots → explicit engine/book → ScheduledSlot 2 → Task scheduled. The UI displayed the booking confirmation and refreshed the Tasks list.

REJECTED was confirmed without booking; a once overnight commitment (2026-10-09, 22:00–06:00) was created and displayed with its backend-derived overnight state. Backend 422 details were visible without clearing the form.

The API process initially retained code from before time/window hardening. Recommendation 2 returned elapsed candidates and was rejected without booking. Restarting the API loaded the existing guards; the successful recommendation 3 then used future candidates. This required no backend source modification.

npm run build passed and npm run lint passed with no warnings. At frontend validation, the recorded backend automated state was **186 passed, 1 skipped, 0 failed**; the only skip is the credential-gated smoke when credentials are disabled. Those backend tests were not rerun for frontend implementation. The earlier live smoke had passed separately.

Decision and booking remained separate in the UI. The real frontend success complements the earlier fallback E2E and small controlled 5/5 post-chat sample; it is not a reliability guarantee. That phase's proposed backlog is superseded by the completed governance and feature freeze below.



## Deterministic Reason-Code Governance — 2026-10-07

After human approval, Bob began replacing model-owned reason codes with factual backend derivation. Its trial ended with changes already on disk in ai/schemas.py, ai/agent.py and the two planner test files. Bob had added the vocabulary, two-field prompt/schema, derivation helper and initial test updates. Its reported stale-container test result was not trusted.

Codex inspected the working tree and completed only the approved scope: explicit low-priority derivation, strict integer candidate-ID validation, additional derivation/structural regression cases, and exact HTTP/audit assertions. Obsolete tests requiring fallback for model-provided reason codes were removed; extra fields are ignored instead. No provider, engine, database, HTTP contract, frontend, environment or dependency change was required.

The final model contract is recommended_candidate_id + explanation only. The backend derives HIGH_PRIORITY, MEDIUM_PRIORITY or LOW_PRIORITY from task priority; EARLIEST_SLOT from candidate_id=0; ONLY_SLOT_AVAILABLE from a one-candidate list; and DEADLINE_CLOSE when a deadline exists and its date minus the selected candidate date is at most one day. PROVIDER_FALLBACK remains system-only. MOST_BUFFER_BEFORE_DEADLINE was removed. Fallback remains for provider failure, malformed JSON, structurally invalid output and invalid candidate IDs, retaining the first valid deterministic candidate and existing explanation.

Validation used the actual local backend source mounted read-only, with real watsonx credentials disabled: **216 passed, 1 skipped, 0 failed**. The only skip is the credential-gated smoke. Two existing warnings remain: SQLAlchemy nullable date annotation and Starlette/httpx. git diff --check passed. The former time-dependent booking test is deterministic and runs normally.

The earlier real smoke, 2/5 → 5/5 chat comparison and real human-in-the-loop frontend flow are historical evidence; they were not rerun after this final contract change. Deterministic reason codes resolve the observed code-semantic issue, but do not guarantee free-text explanation accuracy or production reliability.

## Current MVP Feature Freeze

ST-1 through ST-9, ST-8 cleanup, time/window hardening, frontend MVP and deterministic reason-code governance are complete. The current MVP is feature-frozen. Architecture decisions remain closed; no new backend feature or Auditor Agent is planned.

1. Visual polish.
2. Deployment.
3. Screenshots/GIF/demo evidence.
4. Presentation/LinkedIn.
5. Optional real-world usage.
