# watsonx Validation Record

Status: **complete**, including real provider validation, backend human-in-the-loop flow, chat transport migration and the subsequent frontend-backed real flow. Updated 2026-10-07. This file replaces obsolete text-generation implementation instructions with the validated current state.

## Runtime and Connectivity

IBM watsonx project and Runtime configuration, real IBM Cloud API authentication, and WatsonxProvider model calls were validated.

- Provider: watsonx.
- Validated runtime model: meta-llama/llama-3-3-70b-instruct.
- SDK used for chat validation: ibm-watsonx-ai 1.8.0.
- Current code default model: granite-4-1-8b, distinct from the validated environment.

The available Lite/Sydney runtime did not support the planned IBM Granite model. The current non-IBM model runs through IBM watsonx. Future Granite validation may require another supported region/runtime/deployment; no alternative provider was added.

Original ST-9 work is complete: provider response handling, credential-gated smoke test, and the corrected .env.example template. Historical generate_text extraction instructions are superseded by chat. No credentials belong in this document.

## Provider Smoke Validation

The credential-gated test passed separately with a real watsonx call: **1 passed**. It checks that WatsonxProvider.complete() returns a nonempty string; it does not validate PlannerAgent JSON or booking. With credentials disabled, this is the only test skipped in the latest suite (216 passed, 1 skipped, 0 failed). The recorded live result was not rerun during frontend implementation or this documentation update.

## Text Generation → Chat Migration

WatsonxProvider.complete() moved from deprecated text generation to ModelInference.chat(). The real model/API accepted:
```json
{
  "temperature": 0,
  "max_tokens": 512,
  "response_format": {"type": "json_object"}
}
```

At transport migration the PlannerAgent prompt was unchanged. The current two-field prompt is sent as one user message. The provider extracts choices[0].message.content and returns only a string through complete(prompt) -> str. It does not parse JSON or validate candidate IDs/reason codes. Invalid transport shapes and upstream errors become ProviderError.

At transport migration PlannerAgent retained its existing parsing and model reason-code guards. Subsequent deterministic reason-code governance replaced model-owned codes with backend derivation, as recorded below; json.loads, Pydantic validation, candidate bounds and deterministic lookup/fallback remain. Provider/model audit metadata remains sourced from the injected instance. The transport migration required no prompt changes, retries without JSON mode, or architectural workarounds were necessary.

The deprecated /ml/v1/text/generation warning disappeared from the real support probe, smoke test and five-call comparison. Existing test and third-party license warnings remain.

## Controlled Reliability Comparison — Before Final Reason-Code Governance

The same five pending test scenarios and deterministic candidate context were used before and after migration (Tasks 3–7, from_date 2026-10-08).

| Scenario | Candidates | Before | After candidate ID | After reason codes |
|---|---:|---|---:|---|
| High priority, close deadline / Task 3 | 10 | Valid | 0 | EARLIEST_SLOT, DEADLINE_CLOSE, HIGH_PRIORITY |
| Medium priority / Task 4 | 10 | Fallback | 6 | MEDIUM_PRIORITY, EARLIEST_SLOT |
| Longer duration / Task 5 | 10 | Fallback | 7 | HIGH_PRIORITY, MOST_BUFFER_BEFORE_DEADLINE |
| Multiple valid candidates / Task 6 | 10 | Fallback | 0 | MEDIUM_PRIORITY, EARLIEST_SLOT |
| Only one valid candidate / Task 7 | 1 | Valid | 0 | DEADLINE_CLOSE, HIGH_PRIORITY, ONLY_SLOT_AVAILABLE |

**Before:** 2/5 structured responses valid; 3/5 deterministic fallbacks.
**After:** 5/5 structured responses valid; 0/5 fallbacks.

All three earlier failures were malformed JSON, not connectivity failures:
- Task 4: unquoted reason_codes; markdown fences were removable, but the JSON remained invalid.
- Task 5: unquoted reason_codes.
- Task 6: unquoted reason_codes, repeated objects/prose and an incomplete ending consistent with truncation. Finish metadata was not captured, so truncation was not independently confirmed.

All three failed json.loads with `Expecting value: line 3 column 20 (char 54)`. No post-chat fallback occurred, so there is no raw failure reason for that round.

This is a small controlled sample, not a reliability guarantee or production failure-rate estimate. Structural validity is not semantic accuracy: candidate 6 received EARLIEST_SLOT, and a later candidate received MOST_BUFFER_BEFORE_DEADLINE. At that time guards validated code membership rather than factual derivation. The final governance change resolves this reason-code issue; the historical table is not the current vocabulary.

The comparison called the real PlannerAgent path directly with a capture-only provider wrapper. It did not insert new audit rows or book tasks; Tasks 3–7 remained pending. Raw failure output was captured locally for diagnosis only, never in ai_recommendations. No raw output or credentials are reproduced here.

## Backend E2E Validation — Pre-Chat

The persisted real flow was completed before chat migration, using recommendation_id=1 with fallback_used=true:

Task → deterministic engine → valid candidates → real watsonx call → PlannerAgent fallback → persisted AIRecommendation → human APPROVED → explicit engine/book → current-state revalidation → ScheduledSlot.

| Action/check | Recorded result |
|---|---|
| POST /api/v1/planner/recommend | HTTP 201; Task 1; recommendation_id=1; deterministic valid recommended slot; fallback_used=true |
| Audit persistence | provider=watsonx; model_id=meta-llama/llama-3-3-70b-instruct; candidates, reason_codes, explanation and fallback flag persisted |
| POST /api/v1/planner/decision, APPROVED | HTTP 200; final_start/end equal persisted recommendation |
| After decision | Task remained pending; no ScheduledSlot existed |
| POST /api/v1/engine/book with approved final_start | HTTP 201; ScheduledSlot 1 created |
| After explicit booking | Task 1 became scheduled |

Selected slot: 2026-10-08 08:00–09:00. Approval did not book automatically. Booking recomputed end and revalidated current commitments, scheduled conflicts and deadline before the atomic write.

This pre-chat backend run demonstrates safe fallback and action separation. The later frontend run below separately demonstrates the persisted post-chat flow without fallback. The original recommendation's raw parsing failure was not recorded; later controlled failures supplied the malformed-JSON diagnosis.

The historical watsonx-e2e-validation-report.md retains detailed pre-chat requests/responses. Its text-generation warning and malformed-output observations describe that earlier phase.

At the time of this real validation, booking lacked an explicit daily work-window guard. A subsequent approved deterministic fix now enforces the full interval within the configured start-date window and excludes nonfuture suggestions. Its isolated suite passed with 186 passed, 1 skipped, 0 failed; no real watsonx calls were rerun for that fix.

## Frontend MVP Validation — Post-Chat, Before Final Reason-Code Governance

This validation is distinct from the provider smoke and the five-call reliability comparison. The React/TypeScript/Vite one-page MVP used the actual backend through the Vite /api → http://localhost:8000 development proxy; backend CORS and API contracts were unchanged.

| Step | Observed result |
|---|---|
| Create task through Tasks panel | Task 8, 30 minutes, high priority, no deadline, pending |
| Request real planner recommendation | recommendation_id=3; fallback_used=false; full original candidate list displayed |
| MODIFIED | Selected original candidate 2026-10-07 14:00–14:30; decision recorded |
| Before booking | Task 8 remained pending; zero ScheduledSlots for the task, verified through existing read endpoints |
| Click Book selected slot | Explicit engine/book using recommendation.task_id and decision.final_start |
| After booking | ScheduledSlot 2 created; Task 8 became scheduled; Tasks list refreshed |

REJECTED was also confirmed with no Book button and no booking. A once commitment on 2026-10-09 from 22:00 to 06:00 was created and displayed with the returned “Ends next day” state.

The UI keeps the complete recommendation snapshot. MODIFIED cannot select outside its original candidate list. Original datetime strings are sent unchanged; display formatting performs no UTC conversion. Decisions and booking remained separate UI actions.

Frontend validation: npm run build passed; npm run lint passed with no warnings. No Vitest, React Testing Library or other dependencies were added. No automated interaction test runner exists yet.

During validation, the running API initially retained pre-hardening code and returned elapsed candidates for recommendation 2. That recommendation was rejected without booking. Restarting only the API loaded the already-existing guards; recommendation 3 then returned future candidates. No backend files or environment values were changed for the frontend validation.

The frontend flow is additional end-to-end evidence, not an expansion of the controlled 5/5 reliability sample or a reliability guarantee. It did not rerun the credential-gated smoke test.

## Automated and Live Test Evidence

Recorded commands:
```text
docker compose up -d --build api
docker compose exec -T api python -m pip install pytest
docker compose exec -T -e WATSONX_API_KEY= api python -m pytest tests -q -p no:cacheprovider
docker compose exec -T api python -m pytest tests/test_watsonx_provider.py -v -p no:cacheprovider
```

pytest installation was container-only. The isolated suite used SQLite dependency overrides, not development MySQL.

- Historical chat-migration suite: **160 passed, 1 skipped, 0 failed**, 59 warnings. Credentials were disabled; this run skipped the live smoke test.
- Historical suite after deterministic time/window hardening: **186 passed, 1 skipped, 0 failed**, 2 warnings. Its only skip is the credential-gated smoke with credentials disabled.
- Final governance suite on read-only-mounted local source: **216 passed, 1 skipped, 0 failed**, 2 warnings; credentials disabled, only live smoke skipped.
- Separate credential-gated real smoke: **1 passed**, 3 warnings.
- Eight mocked chat transport cases cover parameters, unchanged text delivery to PlannerAgent, response-shape errors and upstream errors.
- Smoke asserts a nonempty string, not PlannerAgent schema validity, and does not print raw output.
- The pre-existing time-dependent booking test was subsequently rewritten with a fixed shared clock; its time-of-day skip is removed.

Historical warnings included nullable date annotation, utcnow test helpers, Starlette/httpx and third-party model licensing. The latest isolated suite reported only SQLAlchemy nullable date and Starlette/httpx warnings. The text-generation API warning is gone.

## Scope and Remaining Work

Migration files: backend/app/ai/provider.py, backend/tests/test_watsonx_chat.py and this documentation. Prompt, provider interface, audit metadata, deterministic engine, routes and fallback behavior remained unchanged.

No raw model output was persisted. No secrets were exposed or changed. The chat migration introduced no new agents, routes, tables or frontend features. The separately approved frontend MVP was implemented later without changing backend contracts.

## Final Deterministic Reason-Code Contract and Feature Freeze

The model returns only recommended_candidate_id and explanation. PlannerAgent derives reason_codes from task/candidate facts after structural and candidate-ID validation:

| Code | Deterministic rule |
|---|---|
| HIGH_PRIORITY | task.priority == "high" |
| MEDIUM_PRIORITY | task.priority == "medium" |
| LOW_PRIORITY | task.priority == "low" |
| EARLIEST_SLOT | selected candidate_id == 0 |
| ONLY_SLOT_AVAILABLE | len(candidate_slots) == 1 |
| DEADLINE_CLOSE | deadline exists and (deadline - selected_candidate.date).days <= 1 |
| PROVIDER_FALLBACK | System-only fallback path |

MOST_BUFFER_BEFORE_DEADLINE is removed. Extra model fields, including reason_codes, are ignored. Fallback occurs only for provider failure, malformed JSON, structurally invalid output or invalid candidate_id. Existing fallback selects candidate 0 and supplies only PROVIDER_FALLBACK. Provider transport, audit metadata, HTTP schemas and raw-output exclusion are unchanged; historical audit records are not rewritten.

The 5/5 post-chat sample, separate live smoke and real recommend → decision → explicit book flow preceded final governance. They were not rerun against the final two-field contract. The sample is small and provides no reliability guarantee. The final local automated suite is **216 passed, 1 skipped, 0 failed**; the only skip is the credential-gated smoke with credentials disabled. See deterministic-reason-codes-plan.md for source-tree validation details.

The current MVP is **feature-frozen**. Next priorities:

1. Visual polish.
2. Deployment.
3. Screenshots/GIF/demo evidence.
4. Presentation/LinkedIn.
5. Optional real-world usage.

No new backend features or Auditor Agent are planned; completed architecture decisions remain closed. Granite runtime availability, naive local-time limits, explanation accuracy, existing warnings and sample-size limits remain documented limitations rather than authorization for new development.
