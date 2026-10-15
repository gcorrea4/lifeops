# Real watsonx planner E2E validation — 2026-10-07

Result: human-in-the-loop flow completed using existing fallback recommendation 1. APPROVED returned 200 without booking; explicit /engine/book returned 201 and scheduled Task 1. Real model structured-output validation remains unsuccessful (fallback_used=true).

## Actions
- Read AGENTS.md, README, Week 2, ST-8 and watsonx validation plans and relevant implementation.
- Ran docker compose up -d --build api using existing configuration.
- MySQL is healthy; API is running on port 8000.
- Ran HTTP calls inside API container using urllib against the running Uvicorn server (no TestClient or provider mocks).
- Queried real MySQL via SessionLocal / SQLAlchemy, including SELECT 1 and persisted audit row.
- Created Task 1 and one-off FixedBlock 1; retained both as validation evidence.
- Repeated provider completion once with identical task/candidates for read-only diagnosis; did not persist raw completion.

## HTTP request / response log

```jsonl
{"provider": "watsonx", "model": "meta-llama/llama-3-3-70b-instruct", "key_present": true}
{"method": "GET", "path": "/health", "request": null, "status": 200, "response": {"status": "ok"}}
{"database_select_1": 1, "database": "lifeops"}
{"method": "POST", "path": "/api/v1/tasks/", "request": {"title": "E2E watsonx planner validation", "duration_minutes": 60, "priority": "high", "deadline": "2026-10-10"}, "status": 201, "response": {"id": 1, "user_id": 1, "title": "E2E watsonx planner validation", "duration_minutes": 60, "deadline": "2026-10-10", "priority": "high", "status": "pending", "created_at": "2026-10-07T12:00:17"}}
{"method": "POST", "path": "/api/v1/blocks/", "request": {"title": "E2E validation fixed commitment", "recurrence_type": "once", "date": "2026-10-08", "start_time": "10:00:00", "end_time": "12:00:00"}, "status": 201, "response": {"id": 1, "user_id": 1, "title": "E2E validation fixed commitment", "recurrence_type": "once", "weekday": null, "date": "2026-10-08", "start_time": "10:00:00", "end_time": "12:00:00", "spans_next_day": false, "created_at": "2026-10-07T12:00:17"}}
{"method": "GET", "path": "/api/v1/engine/suggest?task_id=1&from_date=2026-10-08", "request": null, "status": 200, "response": [{"start_datetime": "2026-10-08T08:00:00", "end_datetime": "2026-10-08T09:00:00", "date": "2026-10-08"}, {"start_datetime": "2026-10-08T09:00:00", "end_datetime": "2026-10-08T10:00:00", "date": "2026-10-08"}, {"start_datetime": "2026-10-08T12:00:00", "end_datetime": "2026-10-08T13:00:00", "date": "2026-10-08"}, {"start_datetime": "2026-10-08T13:00:00", "end_datetime": "2026-10-08T14:00:00", "date": "2026-10-08"}, {"start_datetime": "2026-10-08T14:00:00", "end_datetime": "2026-10-08T15:00:00", "date": "2026-10-08"}, {"start_datetime": "2026-10-08T15:00:00", "end_datetime": "2026-10-08T16:00:00", "date": "2026-10-08"}, {"start_datetime": "2026-10-08T16:00:00", "end_datetime": "2026-10-08T17:00:00", "date": "2026-10-08"}, {"start_datetime": "2026-10-08T17:00:00", "end_datetime": "2026-10-08T18:00:00", "date": "2026-10-08"}, {"start_datetime": "2026-10-08T18:00:00", "end_datetime": "2026-10-08T19:00:00", "date": "2026-10-08"}, {"start_datetime": "2026-10-08T19:00:00", "end_datetime": "2026-10-08T20:00:00", "date": "2026-10-08"}]}

{"method": "POST", "path": "/api/v1/planner/recommend", "request": {"task_id": 1, "from_date": "2026-10-08"}, "status": 201, "response": {"recommendation_id": 1, "task_id": 1, "recommended_slot": {"start_datetime": "2026-10-08T08:00:00", "end_datetime": "2026-10-08T09:00:00"}, "reason_codes": ["PROVIDER_FALLBACK"], "explanation": "Default recommendation: first available valid slot selected.", "candidate_slots": [{"start_datetime": "2026-10-08T08:00:00", "end_datetime": "2026-10-08T09:00:00", "date": "2026-10-08"}, {"start_datetime": "2026-10-08T09:00:00", "end_datetime": "2026-10-08T10:00:00", "date": "2026-10-08"}, {"start_datetime": "2026-10-08T12:00:00", "end_datetime": "2026-10-08T13:00:00", "date": "2026-10-08"}, {"start_datetime": "2026-10-08T13:00:00", "end_datetime": "2026-10-08T14:00:00", "date": "2026-10-08"}, {"start_datetime": "2026-10-08T14:00:00", "end_datetime": "2026-10-08T15:00:00", "date": "2026-10-08"}, {"start_datetime": "2026-10-08T15:00:00", "end_datetime": "2026-10-08T16:00:00", "date": "2026-10-08"}, {"start_datetime": "2026-10-08T16:00:00", "end_datetime": "2026-10-08T17:00:00", "date": "2026-10-08"}, {"start_datetime": "2026-10-08T17:00:00", "end_datetime": "2026-10-08T18:00:00", "date": "2026-10-08"}, {"start_datetime": "2026-10-08T18:00:00", "end_datetime": "2026-10-08T19:00:00", "date": "2026-10-08"}, {"start_datetime": "2026-10-08T19:00:00", "end_datetime": "2026-10-08T20:00:00", "date": "2026-10-08"}], "fallback_used": true}}
{"audit_before_decision": {"id": 1, "task_id": 1, "user_id": 1, "created_at": "2026-10-07 12:00:32", "provider": "watsonx", "model_id": "meta-llama/llama-3-3-70b-instruct", "candidate_slots_json": "[{\"start_datetime\": \"2026-10-08T08:00:00\", \"end_datetime\": \"2026-10-08T09:00:00\", \"date\": \"2026-10-08\"}, {\"start_datetime\": \"2026-10-08T09:00:00\", \"end_datetime\": \"2026-10-08T10:00:00\", \"date\": \"2026-10-08\"}, {\"start_datetime\": \"2026-10-08T12:00:00\", \"end_datetime\": \"2026-10-08T13:00:00\", \"date\": \"2026-10-08\"}, {\"start_datetime\": \"2026-10-08T13:00:00\", \"end_datetime\": \"2026-10-08T14:00:00\", \"date\": \"2026-10-08\"}, {\"start_datetime\": \"2026-10-08T14:00:00\", \"end_datetime\": \"2026-10-08T15:00:00\", \"date\": \"2026-10-08\"}, {\"start_datetime\": \"2026-10-08T15:00:00\", \"end_datetime\": \"2026-10-08T16:00:00\", \"date\": \"2026-10-08\"}, {\"start_datetime\": \"2026-10-08T16:00:00\", \"end_datetime\": \"2026-10-08T17:00:00\", \"date\": \"2026-10-08\"}, {\"start_datetime\": \"2026-10-08T17:00:00\", \"end_datetime\": \"2026-10-08T18:00:00\", \"date\": \"2026-10-08\"}, {\"start_datetime\": \"2026-10-08T18:00:00\", \"end_datetime\": \"2026-10-08T19:00:00\", \"date\": \"2026-10-08\"}, {\"start_datetime\": \"2026-10-08T19:00:00\", \"end_datetime\": \"2026-10-08T20:00:00\", \"date\": \"2026-10-08\"}]", "recommended_start": "2026-10-08 08:00:00", "recommended_end": "2026-10-08 09:00:00", "reason_codes": "[\"PROVIDER_FALLBACK\"]", "explanation": "Default recommendation: first available valid slot selected.", "fallback_used": 1, "user_action": null, "final_start": null, "final_end": null}}
STOP: fallback_used=true; real model recommendation not validated

```

## Checks
- Candidate slots match GET /engine/suggest exactly.
- Recommended slot belongs to deterministic candidates.
- Persisted provider: watsonx.
- Persisted model_id: meta-llama/llama-3-3-70b-instruct.
- Persisted fallback_used: 1 (true), matching HTTP response.
- Persisted reason_codes: ["PROVIDER_FALLBACK"], matching HTTP response.
- Persisted explanation: Default recommendation: first available valid slot selected.
- Persisted candidate_slots_json matches deterministic candidates exactly.
- Audit id: 1; task_id: 1; user_id: 1.
- Final user_action: APPROVED; final_start/final_end equal persisted recommended_start/recommended_end.
- After decision, Task remained pending and ScheduledSlot count was 0, confirmed by SQL before booking.
- Final Task status, confirmed by SQL after explicit booking: scheduled.
- ScheduledSlot count for Task 1 after explicit booking: 1 (ScheduledSlot id 1).
- Successful booking exercised the existing deterministic booking endpoint; negative conflict/revalidation cases were not tested in this continuation.

## Continuation: APPROVED and explicit booking

User explicitly authorized continuing recommendation_id=1 despite fallback_used=true.
Executed a Python script through docker compose exec -T api python - using urllib HTTP calls to the running API and fresh SessionLocal SQL reads before decision, after decision/before booking, and after booking.
No new recommendation or provider completion was requested.
All assertions passed; process exit code 0. No new warnings/errors were emitted.

```jsonl
{"before_decision": {"audit": {"id": 1, "task_id": 1, "provider": "watsonx", "model_id": "meta-llama/llama-3-3-70b-instruct", "fallback_used": 1, "user_action": null, "recommended_start": "2026-10-08 08:00:00", "recommended_end": "2026-10-08 09:00:00", "final_start": null, "final_end": null}, "task": {"id": 1, "status": "pending"}, "scheduled_slots": []}}
{"method": "POST", "path": "/api/v1/planner/decision", "request": {"recommendation_id": 1, "action": "APPROVED"}, "status": 200, "response": {"recommendation_id": 1, "action": "APPROVED", "final_start": "2026-10-08T08:00:00", "final_end": "2026-10-08T09:00:00", "message": "Decision recorded. Proceed to POST /engine/book to confirm booking."}}
{"after_decision_before_booking": {"audit": {"id": 1, "task_id": 1, "provider": "watsonx", "model_id": "meta-llama/llama-3-3-70b-instruct", "fallback_used": 1, "user_action": "APPROVED", "recommended_start": "2026-10-08 08:00:00", "recommended_end": "2026-10-08 09:00:00", "final_start": "2026-10-08 08:00:00", "final_end": "2026-10-08 09:00:00"}, "task": {"id": 1, "status": "pending"}, "scheduled_slots": []}}
{"method": "POST", "path": "/api/v1/engine/book", "request": {"task_id": 1, "start_datetime": "2026-10-08T08:00:00"}, "status": 201, "response": {"id": 1, "task_id": 1, "user_id": 1, "start_datetime": "2026-10-08T08:00:00", "end_datetime": "2026-10-08T09:00:00", "created_at": "2026-10-07T12:06:18"}}
{"after_explicit_booking": {"audit": {"id": 1, "task_id": 1, "provider": "watsonx", "model_id": "meta-llama/llama-3-3-70b-instruct", "fallback_used": 1, "user_action": "APPROVED", "recommended_start": "2026-10-08 08:00:00", "recommended_end": "2026-10-08 09:00:00", "final_start": "2026-10-08 08:00:00", "final_end": "2026-10-08 09:00:00"}, "task": {"id": 1, "status": "scheduled"}, "scheduled_slots": [{"id": 1, "task_id": 1, "start_datetime": "2026-10-08 08:00:00", "end_datetime": "2026-10-08 09:00:00"}]}}
{"human_in_the_loop_validation": "passed", "new_recommendations_created": 0}
```

Confirmed slot: 2026-10-08T08:00:00 to 2026-10-08T09:00:00.
Booking occurred only after the separate explicit POST /api/v1/engine/book request.
Audit provider/model/fallback remained watsonx / meta-llama/llama-3-3-70b-instruct / true.

## Cause and limitations
The initial API response exposes fallback only; PlannerAgent suppresses the underlying provider/parsing failure.
The subsequent diagnostic real completion failed JSON decoding with:
Expecting value, line 3, column 20; response length 1859 characters.
This reproduces a malformed-JSON failure but does not prove the initial completion had the identical cause.
No architecture/code/environment changes were made.

## Warnings
- Docker configuration/socket access denied inside sandbox; authorized execution outside sandbox succeeded.
- pip root-user warning during image build; pip upgrade notice.
- watsonx SDK third-party model license warning.
- watsonx SDK: /ml/v1/text/generation deprecated; use /ml/v1/text/chat.
- Earlier git status reported inaccessible .pytest_cache directories.
- No credentials or raw model completion printed or stored in this report.

## Files changed
Only this validation report was created and updated. Application source and .env were not modified.

