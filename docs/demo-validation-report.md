# LifeOps Demo Validation Report

Date of run: 2026-10-10. Scope: demo/evidence validation only. No application code, test, environment, dependency or Docker file was changed. Historical validation records elsewhere are unchanged.

## Environment confirmed before the run

- Run from the repository root (root `.env` loaded); credentials were never printed.
- AI_PROVIDER=watsonx, provider_name=watsonx, model_id=`meta-llama/llama-3-3-70b-instruct`, endpoint `https://au-syd.ml.cloud.ibm.com` (Sydney). SDK ibm-watsonx-ai 1.8.0. Python 3.12.15 in the API container.
- Development MySQL healthy; API `/health` returned `{"status":"ok"}`.
- **Stale container found and fixed.** The `lifeops-api` image dated 2026-10-07 still had the pre-governance contract (`agent.py`/`schemas.py` differed from the local source; `MOST_BUFFER_BEFORE_DEADLINE` present, no `_derive_codes`). Only the `api` service was rebuilt and restarted (`docker compose up -d --build api`; `db` untouched, no code/env/Docker-file change). After the rebuild 10 of 10 checked source files were byte-identical to local and git status was clean. A demo run against the old image would not have validated the final contract.

## Demo records created (development MySQL, all prefixed DEMO)

| Entity | ID | Content |
|---|---|---|
| FixedBlock | 3 | DEMO University class, once, 2026-10-12 09:00-12:00 |
| FixedBlock | 4 | DEMO Part-time work, once, 2026-10-12 14:00-18:00 |
| Task | 9 | DEMO Prepare final project presentation, 60 min, high, deadline 2026-10-13, pending at creation |
| AIRecommendation | 5 | task 9, watsonx, see below |
| ScheduledSlot | 3 | task 9, 2026-10-12 12:00-13:00 |

Pre-existing records (tasks 1-8, blocks 1-2, slots 1-2, recommendations 1-4) were not modified. Row counts after the run: tasks 9, fixed_blocks 4, scheduled_slots 3, ai_recommendations 5.

## Requests performed (API, base `/api/v1`)

1. `POST /blocks/` x2 (above) -> 201, ids 3 and 4; `GET /blocks/` listed both.
2. `POST /tasks/` `{title, duration_minutes: 60, priority: "high", deadline: "2026-10-13"}` -> 201, id 9, status pending.
3. `POST /planner/recommend` `{task_id: 9, from_date: "2026-10-12"}` -> **201**. One real watsonx call.
4. `POST /planner/decision` `{recommendation_id: 5, action: "MODIFIED", chosen_start: "2026-10-12T12:00:00", chosen_end: "2026-10-12T13:00:00"}` -> 200.
5. `POST /engine/book` `{task_id: 9, start_datetime: "2026-10-12T12:00:00"}` -> **201**, slot id 3.

## Results

- **Recommendation:** slot 2026-10-12 08:00-09:00 (candidate 0), explanation (model-written): "Earliest slot before deadline".
- **fallback_used:** false.
- **Audit (MySQL):** provider=watsonx, model_id=meta-llama/llama-3-3-70b-instruct.
- **reason_codes (backend-derived):** HIGH_PRIORITY, EARLIEST_SLOT, DEADLINE_CLOSE (priority high; candidate 0; deadline 2026-10-13 minus candidate date 2026-10-12 = 1 day).
- **Candidates (deterministic engine, 10):** 10-12 08:00, 12:00, 13:00, 18:00, 19:00, 20:00, 21:00; 10-13 08:00, 09:00, 10:00 (each 60 min). None overlaps 09:00-12:00 or 14:00-18:00.
- **Human decision:** MODIFIED to original candidate [1], 12:00-13:00 (between class and work). Audit: user_action=MODIFIED, final 12:00-13:00, recommended slot unchanged at 08:00-09:00.
- **Task state before booking (after decision):** pending; no ScheduledSlot for task 9 (total slots still 2).
- **Task state after booking:** scheduled; ScheduledSlot 3 = 12:00-13:00, identical to the modified choice (total slots 3).

## Warnings and unexpected behavior

1. **Container clock is UTC.** `clock.now()` inside the API container returned 2026-10-10T23:31 while the host (UTC-3) was 20:31. This is the documented naive-datetime limitation, but it affects demos: "now", "today" and the future-only cutoff follow the container clock, and `created_at` is also UTC. No code was changed.
2. **The UI does not send `from_date`** (`api.recommend({ task_id })`), so the default is the container's "today". This run used an explicit `from_date` through the API. For a UI capture, commitments must lie in the candidate window the UI will request: with a UTC container and host UTC-3, an evening session (about 18:00-23:59 local) with commitments dated the next local day is expected to work. This recommendation is **not verified** in the UI; check the first recommendation before recording.
3. The model chose candidate 0 (earliest), as in most of the earlier sample. The MODIFIED decision is what shows human control.
4. The demo task is consumed by booking (scheduled). A re-run needs a new pending DEMO task; do not delete demo rows without separate approval.
5. Existing watsonx third-party license warning appears in live runs; not an error.

## Repeatable setup recipe

1. Rebuild/restart the API after any code change (`docker compose up -d --build api`) and compare file hashes with the local source.
2. Choose a capture day D. Create two `once` FixedBlocks dated D: class 09:00-12:00 and work 14:00-18:00 (titles starting "DEMO").
3. Create one pending Task: "DEMO Prepare final project presentation", 60 min, high, deadline D+1.
4. Run the flow through the UI (below) or the API sequence above. Expect HIGH_PRIORITY + DEADLINE_CLOSE always, EARLIEST_SLOT only when the model picks candidate 0.
5. Never record an `.env`, terminal showing keys, or network panel with headers.

## Screenshot checklist

| ID | Screen | Must be visible | Caption |
|---|---|---|---|
| A1 | Tasks panel | DEMO task, 60 min, high, deadline, status pending | "A pending task with a priority and a deadline." |
| A2 | Fixed commitments | DEMO University class and DEMO Part-time work | "Real commitments the engine must respect." |
| B | Plan a task, review phase | Recommended slot, explanation, reason-code badges, "Fallback used: No", all candidates (none inside 09-12 or 14-18), "Recommended" badge on candidate 0 | "The engine finds valid slots; watsonx picks one by ID; the backend derives the reason codes." |
| C | After MODIFIED | Selected non-recommended candidate, "Decision recorded. Task is still pending.", note that booking is separate, Tasks panel still pending | "The human changed the choice. Nothing is booked yet." |
| D | After Book | "Booking confirmed" with the ScheduledSlot, Tasks panel status scheduled | "Explicit booking revalidated and scheduled the task." |
| E (optional) | Terminal/MySQL | ai_recommendations row: provider watsonx, model id, reason_codes, user_action MODIFIED, final slot | "Auditable record: provider, model, codes, human decision." |

Do not capture the `.env`, API keys or request headers.

## GIF / video sequence (about 45-60 s)

1. (0-6 s) Page overview: Tasks and Fixed commitments panels (A1, A2).
2. (6-10 s) Click the DEMO task, then "Get recommendation" (button label per UI) in Plan a task. Wait for the response (real model call, a few seconds).
3. (10-22 s) Pause on the result: recommended slot, explanation, reason codes, "Fallback used: No", candidate list (B). Hover or point at the gap around 09-12 and 14-18.
4. (22-32 s) Select candidate 12:00-13:00, click "Modify to selected candidate" (C). Show "Decision recorded. Task is still pending." and the pending task in Tasks.
5. (32-42 s) Click "Book selected slot". Show "Booking confirmed" (D) and the Tasks panel flipping to scheduled.
6. (42-50 s) Optional: switch to the terminal for the audit row (E). End on the footer "Recommendations are suggestions. Booking rechecks current availability."

Keep viewport around 1280 px wide; hide bookmarks and notifications; if a fallback occurs, keep it and label it honestly rather than re-running silently.
