# LifeOps Development Log

This chronological record describes the development decisions and validations leading to the current state. Early milestones are ordered by development phase rather than assigned unverified dates. Latest backend validation: 2026-10-07; latest documentation update: 2026-10-10.

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

## Final-Contract Real watsonx Revalidation — 2026-10-10

With explicit user authorization, the real provider (watsonx, meta-llama/llama-3-3-70b-instruct, au-syd) was exercised against the final two-field contract. The credential-gated smoke passed (1 passed). A 10-scenario PlannerAgent sample used synthetic AgentInput directly through WatsonxProvider and PlannerAgent: no database, no audit rows, no bookings, no raw output persisted. Scenarios covered high/medium/low priority, with and without deadlines, one-candidate and multi-candidate lists.

Result: 10/10 valid structured responses, 0 fallbacks, no extra model fields. Reason codes were backend-derived and matched the documented rules in every case (including DEADLINE_CLOSE on a deadline-day and day-before candidate, ONLY_SLOT_AVAILABLE for a single candidate, and no deadline code for a distant deadline). The model chose candidate 0 in 6 of 10 scenarios. Explanations were short and sometimes loosely worded, which is the known free-text limit. The sample is small and synthetic; it does not prove production reliability, and a persisted recommend → decision → book flow on the final contract remains to be captured during the demo. Backend suite re-confirmed locally at 216 passed, 1 skipped, 0 failed before the live calls.

## Persisted Demo Validation on the Final Contract — 2026-10-10

With explicit authorization to write DEMO data to the development MySQL, the full persisted flow was run against real watsonx (meta-llama/llama-3-3-70b-instruct, au-syd). Preflight found the running API container was stale (image from 2026-10-07 with the pre-governance contract); only the api service was rebuilt and its files verified identical to local source before the run. No code, env or Docker file was changed.

Records: FixedBlocks 3 and 4, Task 9, AIRecommendation 5, ScheduledSlot 3. Flow: recommend 201 with fallback_used=false and backend-derived HIGH_PRIORITY, EARLIEST_SLOT, DEADLINE_CLOSE; human MODIFIED to original candidate 12:00–13:00; after the decision the task was still pending with no new slot; explicit book 201 created the slot and the task became scheduled; MySQL confirmed provider watsonx, the model id, the codes, user_action MODIFIED and matching final slot. Observed caveats: container clock is UTC (host UTC-3), the UI sends no from_date, and the UI path was not exercised in this run. Details, screenshot checklist and GIF sequence are in demo-validation-report.md.

## Bilingual UI (EN/PT) — 2026-10-12

At the user's explicit request, the frontend gained a runtime EN/PT language switch with no new dependency: a typed message dictionary, a small React context/provider and a header toggle (choice kept in localStorage, defaulting to the browser language). Only display text changed; payloads, naive datetime strings, reason_code values, model explanations and user-entered titles are untouched, and no backend, contract or business-rule change was made. Known backend error details are translated by exact match; other backend messages (including Pydantic validation text) remain English. Validation: `npm run build` and `npm run lint` passed (lint exit 0); in the browser pane both languages rendered, the toggle persisted, the browser language (pt-BR) was detected by default and no console errors appeared. The planner decision/booking screens were verified by build/type-check only; no live recommendation was requested, so no AI call or database write was made.

## Full Test Pass on the Public Site — 2026-10-14

Everything below was run against `https://boblifeops.vercel.app` (Vercel rewrite, Azure API, Azure MySQL) with one visitor session, driven through the page with DOM events, using real watsonx calls (13 recommendations, all `fallback_used=false`) and DEMO data that was deleted at the end (204, cascade; production empty).

Passed: validations (blank title disables Create; past deadline gives the translated 422; equal times; a 900-minute task gives the translated 422 without calling the AI); weekly and overnight commitments with the right PT labels ("Todo sábado", "Toda quarta-feira", "Termina no dia seguinte"); Reject (PT; no Book button, task stays pending); Modify (PT; Modify disabled until a candidate is chosen, booked slot equals the chosen one); Approve plus Book (EN, dark theme); booking conflict (409 shown, decision and Book button preserved, nothing booked) and its recovery through a new recommendation whose candidates skip the conflicting commitment; the daily limit (10 real recommendations, the 11th through the UI returned 429 with the translated message in EN and PT); reload (tasks, commitments, language, theme and session preserved; the planner flow is cleared by design); another visitor id sees an empty space and the original id gets its data back; mobile 375 px layout with no horizontal overflow.

Observations: the model's free-text explanation was again sometimes imprecise ("Earliest available slot" for a non-first candidate) while the backend-derived codes were correct; `/favicon.svg` is still missing (404); not exercised here: the 24-hour purge (time-based), the F1 cold start after 20 idle minutes, and real mobile devices.

## Public Site Verified After the Session Release — 2026-10-14

With Vercel deployment `acf28f1` (Ready) and the matching API on Azure, the public site `https://boblifeops.vercel.app` was verified: the browser creates its identifier (`lifeops-session`), the footer shows the privacy note, the page starts empty without errors, and the full flow worked through the page (task created, real watsonx recommendation #3 with `fallback_used=false`, approve, explicit book, task scheduled). The same data was visible only with that browser's identifier: another visitor and a request without the header both saw nothing. The test data was deleted (204, cascade) and the production database is empty. The daily recommendation limit was not exercised against production (it would spend real watsonx calls); it was verified in a clean Linux container with the mock provider (11th request returns 429).

## Per-Visitor Data Separation (approved option A) — 2026-10-14

Problem raised by the user: the public site shared one dataset (hard-coded `user_id = 1`), so any visitor could see, edit and delete everyone else's plans and spend the watsonx quota. Options discussed: per-browser anonymous sessions, a shared public demo with resets, real login (out of the frozen scope) and not publishing the link. Decision: anonymous session per browser, 24 hours of data lifetime and 10 recommendations per visitor per day.

Implementation (no schema change, no new dependency): `backend/app/core/session.py` with `current_user_id` (reads `X-Session-Id`, 16-64 characters of letters, digits, `_` and `-`, otherwise 400; maps it with SHA-256 to a stable id between 2 and 2^31-2; no header keeps the default user 1), `purge_expired` (lazy cleanup of visitor tasks and commitments older than 24 hours, at most every 30 minutes per process, never blocks the request; slots and recommendations go through the database cascade) and `enforce_recommendation_limit` (HTTP 429 `daily recommendation limit reached`, default user exempt). The tasks, blocks, slots, engine and planner routes and `services/planner.py` now take the user id from the dependency instead of a constant; the audit row takes `task.user_id`. Frontend: `api/client.ts` creates a random identifier stored in localStorage (memory fallback) and sends it on every request; PT/EN messages for the limit, a footer note ("your data is private to this browser and deleted 24 hours after it is created"). The database `created_at` columns are UTC, so the cutoff uses UTC.

Validation: backend suite 235 passed, 1 skipped (16 new tests in `tests/test_sessions.py`: id mapping, invalid ids, isolation of tasks, commitments, slots, booking, suggest, recommendation and decision, daily limit and exemption, purge, rate-limited purge); frontend build and lint passed; local API checked with two visitors; the Linux package was validated in a clean Python 3.12 container (two visitors isolated, 11th recommendation 429) before publishing to Azure. Behavior changes to remember: the local UI now shows a fresh per-browser space (local data stored under user 1 still exists in the database and is reachable without the header); anyone using the API without the header still shares user 1.

## Public Site Verified End to End — 2026-10-14

After the rewrite fix (commit b521590, Vercel deployment success) the public site `https://lifeops-khaki.vercel.app` was verified: `/api/v1/tasks/`, `/blocks/` and `/slots/` return 200 `[]` through Vercel; a full flow through the public domain worked (create task 201, real watsonx recommendation 201 in 7.7 s with `fallback_used=false` and codes HIGH_PRIORITY, EARLIEST_SLOT, DEADLINE_CLOSE, approve 200, book 201, task scheduled); the page itself loaded without errors in PT and dark theme showing the scheduled task, the empty commitments state and the author footer; the test task was then deleted (204, cascade) leaving the production database empty. The commit message of the earlier deploy commit was corrected with an amend and a force-with-lease push (history rewritten on a solo repository). Known leftovers: `/favicon.svg` is referenced but missing (404), the first request after idle takes about 17-20 s (F1 cold start), and the Azure resource group must be deleted after the presentation to stop billing.

## Vercel Rewrite Fix for Trailing Slashes — 2026-10-14

After the first Vercel deploy the page showed HTTP 404 on tasks and commitments. Probing the public site showed the rewrite to Azure worked for paths without a trailing slash (`/api/health` returned the FastAPI JSON 404, `/api/v1/tasks` reached Azure with a 307 after a 17 s cold start) but `/api/v1/tasks/`, the form the frontend uses, was answered by Vercel with its own 404 because `/api/:path*` did not match a trailing slash. `frontend/vercel.json` now uses the pattern `/api/(.*)` with destination `.../api/$1`, which captures the whole path. Frontend paths must keep their trailing slash: without it FastAPI answers 307 with an absolute Azure URL, which a browser would follow cross-origin (no CORS configured). Verified only after the push and redeploy (see the next entry once confirmed).

## Azure API Deployed and Verified — 2026-10-13

The zip was published with `az webapp deploy` ("Site started successfully"; the exit code 255 seen in the log was only the output filter). Public API: `https://lifeops-api-xwc56.azurewebsites.net`. Checks against it: `/health` 200 (23 s on the first, cold request, then about 0.5 s), `/api/v1/tasks/`, `/blocks/` and `/slots/` 200 on the new empty Azure MySQL (tables created by the app at startup), a task created (201), a real watsonx recommendation (201 in 9.6 s, `fallback_used=false`, codes HIGH_PRIORITY, EARLIEST_SLOT, DEADLINE_CLOSE; first candidate 12:00 local, confirming `TZ=America/Sao_Paulo` works on the server), approve (200, task still pending, zero slots), explicit book (201, task scheduled), a repeated booking refused (409) and deletion of the task with its slot and recommendation (204, cascade fix confirmed on Azure). The test data was deleted; the Azure database is empty again. `frontend/vercel.json` rewrites `/api/*` to the Azure API so the browser never needs CORS. Not yet done: the Vercel project itself (user) and an end-to-end run through the public frontend. Reminder: delete `lifeops-rg` after the presentation.

## Azure Deployment (all-Azure option, paid database for about one week) — 2026-10-13

Decision: the user chose the all-Azure path (A2) and accepted a small cost for roughly one week, to be deleted afterwards. Estimated cost (public prices, US$1 = R$5.02): East US MySQL Flexible Server Burstable B1ms plus 20 GB is about US$0.49 per day (about R$2.5), roughly R$17 per week before card taxes. A budget alert (US$10 per month, notifying the subscription Owner) was created first. Resources in resource group `lifeops-rg`: MySQL Flexible Server `lifeops-mysql-mrhvc` (East US, B1ms, 20 GB, database `lifeops` in utf8mb4, TLS required, firewall for the user's IP and Azure services), App Service plan `lifeops-plan` (F1 free, Linux, South Central US because the F1 quota in East US is 0) and web app `lifeops-api-xwc56` (Python 3.12, startup `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`). Credentials live only in local files outside the repository (C:/Users/Gabriel/Backups/lifeops/azure-mysql.env and azure-app.txt) and in the app settings; nothing secret is in the repo or docs.

Incidents: (1) an interrupted creation attempt had already reached Azure, and stopping the local command did not stop the server-side creation, so a duplicate MySQL server (`lifeops-mysql-yrhq9`) appeared and was deleted within minutes; the surviving server's admin password was reset and the empty database recreated. Lesson: after interrupting an Azure create command, list the resources before retrying. (2) The user's network seems to block outbound TCP 3306 (a public MySQL control host also failed), so the database cannot be reached from this machine; the API reaches it from inside Azure. The user's public IP also changed during the session, so the firewall rule was updated. (3) The first dependency build failed locally (`ibm-cos-sdk` has no wheels); the package was built inside a Python 3.12 Linux container instead and validated in a clean container (`/health`, `/api/v1/tasks/`, `/api/v1/blocks/` 200, `ibm-watsonx-ai 1.8.0`, timezone America/Sao_Paulo) before publishing. The zip (51.6 MB, forward-slash paths, no `./` prefix) is deployed with `WEBSITE_RUN_FROM_PACKAGE=1` and prebuilt dependencies (`PYTHONPATH` points to `.python_packages`).

Limits to remember: F1 has about 60 CPU minutes per day, no Always On (cold start after idle) and no SLA. After the presentation, delete the whole group (`az group delete -n lifeops-rg`) to stop billing.

## Hosting Preparation and Azure Cleanup — 2026-10-13

Plan: Vercel frontend (rewrite of /api to the API URL, no CORS needed), backend on Azure App Service F1 (free), database on a free MySQL service. Findings: the Azure for Students subscription had been disabled because the student credit was spent; the user upgraded it to Pay-As-You-Go (no spending limit), which made the old paid resources bill again. With explicit approval (and a decision to skip the backup because the PostgreSQL server was still starting), the three old resource groups (proclubs-rg, ChallengeSprint_group, rscscp1_group) were deleted; only NetworkWatcherRG remains, with no cost. The Azure MySQL Flexible Server was intentionally NOT created because it is not free. Free MySQL candidate verified in Aiven's documentation: always-free single node, 1 GB storage, 1 GB RAM, max_connections 76, no credit card, but it may power off after inactivity and has no SLA or static IP. Free App Service F1 limits found: about 60 CPU minutes per day, no Always On (the app sleeps when idle), 1 GB RAM and storage, no SLA.

Code prepared for hosting (backend suite 219 passed, 1 skipped; image rebuilt and verified): `backend/requirements.txt` now pins the eight direct dependencies to the validated versions; optional `DB_SSL_CA` setting (`settings.py`, `database.py::_connect_args`, two unit tests, `.env.example`) enables TLS verified against a CA file, empty by default so local behavior is unchanged. Still to do: create the free MySQL, set app settings (database connection, AI_PROVIDER=watsonx, watsonx credentials, TZ=America/Sao_Paulo, DB_SSL_CA), package and deploy to App Service (build the zip with forward-slash paths, per the Windows zip pitfall), verify /health, then point the Vercel rewrite at the API. Expect cold starts on F1 and a possible power-off of the free database after inactivity; present this as a demo MVP.

## Full UI Flow Test and Error Translation Fix — 2026-10-13

A full UI pass (EN and PT, real watsonx, DEMO data cleaned afterwards) covered reject (EN), approve + book (EN), modify (EN/PT), a second recommendation on the same task, a page reload mid-flow, validation errors, weekly and overnight commitments, a task too long for any slot (422, no AI call, no recommendation row), a booking conflict (409 with state preserved) and its recovery through a new recommendation, plus the backend suite (217 passed, 1 skipped), frontend build/lint and the live smoke. One gap found: the past-deadline error stayed English in PT because the backend sends it as `deadline: Value error, deadline must be today or in the future` and the dictionary matched only the bare phrase. Fixed in `api/client.ts` (`translateDetail` matches the exact text or a known detail at the end of each part, and drops the technical prefix); verified in PT and EN, build and lint passed, nothing written to the database.

## Development Database Cleanup and Expired-Task UX — 2026-10-13

Cleanup (user-authorized): a full mysqldump of the development database was written outside the repository (`C:\Users\Gabriel\Backups\lifeops\lifeops-pre-cleanup-20261013-090037.sql`, 17 KB, exit 0, "Dump completed", all four tables present). Old validation/demo records were then deleted through the API: Tasks 1–9 and 11, FixedBlocks 1–5, with their ScheduledSlots 1, 2, 3, 5 and AIRecommendations 1–5 and 7. Preserved: Task 10 "Trabalho" (scheduled), ScheduledSlot 4 and AIRecommendation 6. AUTO_INCREMENT was not reset (next ids: task 12, block 6, slot 6, recommendation 8). Final state verified in MySQL and via the API, and the UI showed only "Trabalho" and the empty commitments state.

Existing backend bug found (NOT fixed, per instruction): `DELETE /api/v1/tasks/{id}` returns HTTP 500 for a task that has a ScheduledSlot (IntegrityError 1048, "Column 'task_id' cannot be null"). The database has ON DELETE CASCADE, but the ORM relationship `Task.scheduled_slot` has no cascade/passive_deletes, so SQLAlchemy first tries to NULL the slot's task_id; the transaction rolls back and nothing is partially deleted. Workaround used: delete the slot first via `DELETE /slots/{id}` (which resets the task to pending), then delete the task. Tasks without a slot delete normally (recommendations cascade in the database). A dedicated, approved fix is needed (for example cascade="all, delete-orphan" or passive_deletes=True with a regression test). The previously documented 422 for a task whose deadline has passed ("no candidate slots") is expected behavior.

Frontend-only UX (no backend, planner or engine change): a pending task whose deadline is before today's local date now shows a text badge "Deadline expired"/"Prazo expirado" (with a "!" marker, not color alone), and its Plan button is disabled (struck-through, outline, tooltip and aria-describedby pointing to the badge). Expired tasks are also left out of the planner's task dropdown. Scheduled/done tasks, tasks with no deadline and tasks due today behave as before. Validated with a simulated task list (the API refuses new tasks with past deadlines and nothing was written to the database): expired, valid, no-deadline, due-today and scheduled-with-past-deadline rows; PT and EN; light and dark; `npm run build` and `npm run lint` passed.

## Massively Template Redesign — 2026-10-13

At the user's request (the previous look felt too generic), the single page was restyled after the "Massively" template by HTML5 UP (CCA 3.0). The user approved the plan and decided: hero image left as a placeholder for their own photo, Google Fonts, dark mode kept and adapted, single page with anchor navigation. Changes are presentation-only: new `#wrapper/#header/#nav/#main/#footer/#copyright` structure in `App.tsx`, a full rewrite of `index.css`/`App.css` (square outline buttons, uppercase Source Sans Pro headings, Merriweather body, pill nav, bordered white or dark main panel, split footer), anchor ids on the panels, hero/nav/footer strings in both languages, a small `useActiveSection` hook and Google Fonts links. The template's jQuery/Scrollex/Font Awesome were not imported; no dependency added. The footer carries the required "Design: HTML5 UP" credit and replaces the template's contact form with an about/principles block. Typography was scaled down from the template (12pt base, 1.9 line height, left-aligned text) for data density, and buttons wrap instead of the template's no-wrap so Portuguese labels fit.

Validation: `npm run build` and `npm run lint` passed (exit 0); fonts loaded from Google; light and dark rendered; EN/PT hero, nav and footer text verified; anchor links scroll to each section and the active menu item follows clicks, scrolling and a return to the top (the first scroll-spy version stuck on the last section because Tasks and Commitments sit side by side; fixed); narrow (mobile) layout checked visually; no console errors. Contrast measured for ~40 text/background pairs in both themes (one real miss found and fixed: light accent text 4.4:1 → `#0a7295` 5.16:1; apparent dark-mode misses were mid-transition artifacts of the hidden browser pane and were re-measured with transitions off: all ≥ 6.87:1). The real recommend/decision/booking flow was not re-run on the new layout (it needs a live watsonx call and database writes) — the planner states were checked with temporary injected markup only. Known follow-ups: (hero photo later dropped in favor of the Bob mascot, see below); `public/favicon.svg` is referenced by index.html but not present.

## Light/Dark Theme Toggle — 2026-10-12

UI-only change requested by the user; no backend, API payload, scheduling, AI, database, Docker or datetime change. Architecture: all colors in index.css/App.css became semantic CSS variables defined in `:root` (light, the existing palette) and overridden in `:root[data-theme="dark"]` (`color-scheme` also switches so native date/time pickers, selects and scrollbars follow). A small typed `theme/` module (`context.ts` with `useTheme`, `ThemeProvider.tsx`) mirrors the i18n pattern: the manual choice is saved in localStorage (`lifeops-theme`); with no saved choice the app follows `prefers-color-scheme` live. An inline script in index.html applies the theme before first paint to avoid a light flash. A compact sun/moon icon button sits beside EN | PT with aria-label and tooltip from the i18n dictionary (EN "Switch to dark mode"/"Switch to light mode"; PT "Ativar modo escuro"/"Ativar modo claro"); EN/PT buttons gained aria-labels ("English"/"Português"). No dependency added.

Validation: `npm run build` and `npm run lint` passed (lint exit 0). In the browser pane: dark by system preference with nothing saved; toggle switched themes without reload and updated aria-label, color-scheme and storage; the saved light choice persisted across reload even though the system was dark; label text, `lang` and pressed state were correct in all four combinations (light/dark × EN/PT); no console errors; keyboard Tab reached the toggle with a visible focus ring in both themes and Enter activated it; the mobile (375 px) header fit without horizontal overflow. Contrast measured on text/background pairs (including temporary injected markup for recommendation, candidate, fallback, error, decision and confirmation states, with no network call, AI call or database write): all ≥ 4.5:1 in both themes (lowest 4.98 light, 5.14 dark). Status and fallback are conveyed by text (and the status dot), not color alone. The real recommend/decision/booking screens were not re-run in dark mode with live data.

## Portuguese UI Flow Validation (real watsonx) — 2026-10-12

Driven entirely through the UI with PT selected, against the development MySQL and real watsonx (meta-llama/llama-3-3-70b-instruct). Records (DEMO-prefixed): FixedBlock 5 ("DEMO Aula de Banco de Dados (UI PT)", 13/10 09:00–12:00), Task 11 ("DEMO Preparar apresentação final (UI PT)", 60 min, high, deadline 14/10), AIRecommendation 7, ScheduledSlot 5. Flow: recommend (fallback_used=false; HIGH_PRIORITY, EARLIEST_SLOT, DEADLINE_CLOSE; recommended 13/10 12:00–13:00, the first free slot because task 10 already held 08:00–09:00 and the DEMO class 09:00–12:00) → human MODIFIED to the original candidate 14:00–15:00 → UI showed "Decisão registrada. A tarefa continua pendente."; MySQL confirmed user_action=MODIFIED, final 14:00–15:00, zero slots, task pending → explicit "Agendar horário selecionado" → "Agendamento confirmado", ScheduledSlot 5 14:00–15:00, task scheduled. Switching to EN rendered the same live state correctly (booking confirmation, candidates, "Recommended" badge, "Fallback used: No", scheduled task); after a reload the persisted task/commitment lists rendered correctly in EN (the local planner flow is lost on reload by design). A PT text scan found no untranslated UI strings. Observed: the model's explanation is English ("Earliest slot before deadline") in both languages because the prompt is English and explanations are intentionally not translated; one PT grammar slip ("Toda sábado/domingo" in weekly commitment labels) was fixed in messages.ts (copy only; build and lint re-run, not re-rendered). Pre-existing records, including the user's own task 10 / recommendation 6 / slot 4, were not modified.

## Visual Polish — Completed

Presentation-only CSS polish was completed after the feature freeze (commit 2d2b9eb), touching only frontend App.css and index.css: typography, spacing, panels, forms, status badges, selection, messages, empty states, focus and responsiveness. No backend, React component, API contract, logic, environment or dependency change. Frontend build and lint passed without warnings.

## Current Next Priorities (updated 2026-10-10)

Visual polish is complete and no longer pending.

1. Repeatable demo and evidence capture: persisted API-level flow validated 2026-10-10; UI screenshots/GIF still to be captured (checklist in demo-validation-report.md).
2. Final real watsonx revalidation on the two-field contract: smoke and 10-scenario sample done 2026-10-10; a persisted end-to-end flow is still to be captured with the demo (live calls need explicit authorization).
3. Deployment planning.
4. Presentation/LinkedIn.
5. Optional real-world usage.

## Repository Hygiene — 2026-10-10

Tracked Python bytecode (__pycache__/*.pyc) was removed from version control and Python cache patterns were added to .gitignore. No source, test, environment, dependency or Docker file changed.

## Task Delete Cascade Fix — 2026-10-13

Fixed technical debt item 12: `DELETE /api/v1/tasks/{id}` returned HTTP 500 (`IntegrityError`, "Column 'task_id' cannot be null") for a task that had a ScheduledSlot, because `Task.scheduled_slot` had no cascade and the ORM tried to NULL `scheduled_slots.task_id` before the database `ON DELETE CASCADE` could act (the transaction rolled back; nothing was partially deleted). Smallest change: `cascade="all, delete-orphan"` on `Task.scheduled_slot` in `backend/app/models/task.py`. Deleting a task now removes its slot and, via the database FK cascade, its AIRecommendation rows; tasks without a slot behave as before, and `DELETE /slots/{id}` is unaffected. No schema, API contract or scheduling change.

Tests: added `test_delete_task_with_slot_and_recommendation_cascades` in `backend/tests/test_tasks.py` (task + slot + recommendation, expects 204 and all three gone); verified it fails against the old model with the same NOT NULL error. While writing it, a latent test-infrastructure bug surfaced: `_truncate_all` in `tests/conftest.py` issued `PRAGMA foreign_keys=ON` inside an open transaction (a no-op), so after the first test FK enforcement stayed OFF on the shared connection. It now re-enables FKs after the commit, so the suite really runs with foreign keys enforced (no other test depended on them being off). Isolated SQLite suite: **217 passed, 1 skipped, 0 failed** (was 216 passed, 1 skipped). Development MySQL was not used; nothing was committed.
