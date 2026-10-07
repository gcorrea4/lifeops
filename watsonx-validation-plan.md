# watsonx Validation Record

Status: **complete**, including real provider validation, human-in-the-loop flow, and the chat transport migration. Updated 2026-10-07. This file replaces obsolete text-generation implementation instructions with the validated current state.

## Runtime and Connectivity

IBM watsonx project and Runtime configuration, real IBM Cloud API authentication, and WatsonxProvider model calls were validated.

- Provider: watsonx.
- Validated runtime model: meta-llama/llama-3-3-70b-instruct.
- SDK used for chat validation: ibm-watsonx-ai 1.8.0.
- Current code default model: granite-4-1-8b, distinct from the validated environment.

The available Lite/Sydney runtime did not support the planned IBM Granite model. The current non-IBM model runs through IBM watsonx. Future Granite validation may require another supported region/runtime/deployment; no alternative provider was added.

Original ST-9 work is complete: provider response handling, credential-gated smoke test, and the corrected .env.example template. Historical generate_text extraction instructions are superseded by chat. No credentials belong in this document.

## Text Generation → Chat Migration

WatsonxProvider.complete() moved from deprecated text generation to ModelInference.chat(). The real model/API accepted:
```json
{
  "temperature": 0,
  "max_tokens": 512,
  "response_format": {"type": "json_object"}
}
```

The unchanged PlannerAgent prompt is sent as one user message. The provider extracts choices[0].message.content and returns only a string through complete(prompt) -> str. It does not parse JSON or validate candidate IDs/reason codes. Invalid transport shapes and upstream errors become ProviderError.

PlannerAgent retains json.loads, Pydantic validation, reason-code membership, reserved fallback-code rejection, candidate bounds and deterministic lookup/fallback. Provider/model audit metadata remains sourced from the injected instance. No prompt changes, retries without JSON mode, or architectural workarounds were necessary.

The deprecated /ml/v1/text/generation warning disappeared from the real support probe, smoke test and five-call comparison. Existing test and third-party license warnings remain.

## Controlled Reliability Comparison

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

This is a small controlled sample, not a reliability guarantee or production failure-rate estimate. Structural validity is not semantic accuracy: candidate 6 received EARLIEST_SLOT, and a later candidate received MOST_BUFFER_BEFORE_DEADLINE. Existing guards validate membership, not the truth of these explanations.

The comparison called the real PlannerAgent path directly with a capture-only provider wrapper. It did not insert new audit rows or book tasks; Tasks 3–7 remained pending. Raw failure output was captured locally for diagnosis only, never in ai_recommendations. No raw output or credentials are reproduced here.

## Real End-to-End Validation

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

This demonstrates safe fallback and action separation. It does not claim that a post-chat nonfallback recommendation repeated the entire persisted booking flow. The original recommendation's raw parsing failure was not recorded; later controlled failures supplied the malformed-JSON diagnosis.

The historical watsonx-e2e-validation-report.md retains detailed pre-chat requests/responses. Its text-generation warning and malformed-output observations describe that earlier phase.

Booking currently lacks an explicit daily work-window boundary check beyond its deadline ceiling; generated candidates are constrained by the work window. The successful valid-candidate booking must not be presented as proof that every arbitrary booking input is guarded.

## Automated and Live Test Evidence

Recorded commands:
```text
docker compose up -d --build api
docker compose exec -T api python -m pip install pytest
docker compose exec -T -e WATSONX_API_KEY= api python -m pytest tests -q -p no:cacheprovider
docker compose exec -T api python -m pytest tests/test_watsonx_provider.py -v -p no:cacheprovider
```

pytest installation was container-only. The isolated suite used SQLite dependency overrides, not development MySQL.

- Full automated suite: **160 passed, 1 skipped, 0 failed**, 59 warnings. Credentials were disabled; this run skipped the live smoke test.
- Separate credential-gated real smoke: **1 passed**, 3 warnings.
- Eight mocked chat transport cases cover parameters, unchanged text delivery to PlannerAgent, response-shape errors and upstream errors.
- Smoke asserts a nonempty string, not PlannerAgent schema validity, and does not print raw output.
- The pre-existing time-dependent booking test can skip at other execution times.

Warnings include the nullable date annotation, utcnow test helpers, Starlette/httpx and third-party model licensing. The text-generation API warning is gone.

## Scope and Remaining Work

Migration files: backend/app/ai/provider.py, backend/tests/test_watsonx_chat.py and this documentation. Prompt, provider interface, audit metadata, deterministic engine, routes and fallback behavior remained unchanged.

No raw model output was persisted. No secrets were exposed or changed. No new agents, routes, tables or frontend features were introduced.

Future scoped priorities: semantic reason-code consistency, larger reliability samples, supported Granite validation, deterministic booking boundary review and clock-dependent test cleanup. These are not part of the completed migration.
