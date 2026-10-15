# Deterministic Reason-Code Governance — Completed Implementation Record

## Status

**Complete; current MVP feature-frozen.** Final validated backend suite: **216 passed, 1 skipped, 0 failed**. The only skipped test is the credential-gated watsonx smoke when credentials are disabled.

This record supersedes the initial pending draft: the approved final vocabulary has seven members, including LOW_PRIORITY. Low-priority tasks do not receive an empty list merely because they are low priority. Earlier six-member examples and approximate test-count estimates were obsolete.

## Final Model Contract

```json
{
  "recommended_candidate_id": 0,
  "explanation": "This valid candidate offers an early start."
}
```

The model no longer owns reason_codes. PlannerAgent performs fence removal, json.loads, Pydantic structural validation, strict integer candidate-ID checks, bounds validation and deterministic lookup. IDs supplied as booleans, strings or floats are invalid. Extra model fields are ignored and cannot override derived codes. The existing 200-character explanation limit remains.

## Final Deterministic Rules

Rules are evaluated only after the selected candidate ID is validated.

| Code | Deterministic rule |
|---|---|
| HIGH_PRIORITY | task.priority == "high" |
| MEDIUM_PRIORITY | task.priority == "medium" |
| LOW_PRIORITY | task.priority == "low" |
| EARLIEST_SLOT | selected candidate_id == 0 |
| ONLY_SLOT_AVAILABLE | len(candidate_slots) == 1 |
| DEADLINE_CLOSE | deadline exists and (deadline - selected_candidate.date).days <= 1 |
| PROVIDER_FALLBACK | System-only fallback path |

Multiple codes can apply. Deadline proximity uses calendar-date subtraction against the selected candidate, not wall-clock time or a rolling 48-hour interval. Upstream deterministic candidates already satisfy scheduling constraints. MOST_BUFFER_BEFORE_DEADLINE is removed.

A successful recommendation receives factual derived codes. Fallback retains its existing first-candidate selection, concise default explanation, fallback_used=true and the single code PROVIDER_FALLBACK; it does not add the normal derived codes.

## Fallback and Preserved Invariants

Fallback is limited to:
- ProviderError / provider failure;
- malformed JSON;
- structurally invalid output, including missing or invalid required fields;
- invalid candidate_id, including negative or out-of-range values.

A model-supplied reason code no longer causes fallback: ignored extra fields have no authority. Empty candidate lists cannot produce a recommendation; the route returns 422 before a provider call or audit insert.

The deterministic engine remains authoritative. AI never invents availability or datetimes. Recommend, decision and explicit engine/book remain separate; decision never books, and booking revalidates current availability.

HTTP reason_codes remains list[str], audit persistence remains the existing JSON-array column, and metadata comes from the injected provider. No database migration or historical audit-row rewrite occurred. Raw model output and hidden chain-of-thought are never persisted. Model-generated explanation prose can still be inaccurate even though codes are factual.

## Completed Scope and Handoff

| File | Completed change |
|---|---|
| backend/app/ai/schemas.py | Seven-member ReasonCode vocabulary; removed MOST_BUFFER_BEFORE_DEADLINE; deterministic semantics documented |
| backend/app/ai/agent.py | Two-field prompt/output schema, strict integer candidate IDs, pure derivation helper, removal of model-code guards |
| backend/tests/test_planner_agent.py | Two-field fixtures, obsolete model-code fallback tests removed, derivation and structural regression coverage |
| backend/tests/test_planner_router.py | Two-field mock response and exact deterministic HTTP/audit assertions |

Bob had already implemented the initial schema, prompt, helper and test changes on disk when its trial ended. Codex reviewed those actual files and completed explicit LOW_PRIORITY handling, strict candidate-ID validation, additional regression cases and exact router/audit assertions. Bob's stale-container test report was not accepted as evidence.

No provider, engine, planner service/router, database model, HTTP schema, frontend, environment or dependency files changed for this feature.

## Completed Test Coverage

- High, medium and low priority; unknown priority does not silently become low.
- Earliest and non-earliest selection; one and multiple candidates.
- Deadline on the same day, next day, farther away or absent.
- Combinations and use of the selected candidate date.
- Extra model reason_codes, including unknown/reserved values, are ignored.
- Prompt/vocabulary checks, strict candidate-ID types, malformed/invalid structure and bounds.
- Provider failure and deterministic fallback retain PROVIDER_FALLBACK.
- Exact recommendation-response and persisted audit code values.

The obsolete tests expecting fallback for unknown model codes or model-supplied PROVIDER_FALLBACK were removed because those model-owned paths no longer exist.

## Validation Against Actual Local Source

The final run used the local backend mounted read-only, avoiding the stale container copy. Real credentials were disabled and AI_PROVIDER=mock; integration tests used isolated SQLite rather than development MySQL.

Recorded PowerShell command:

```text
docker run --rm --mount 'type=bind,source=C:\Users\Gabriel\Desktop\lifeops\backend,target=/app,readonly' -w /app -e WATSONX_API_KEY= -e AI_PROVIDER=mock -e PYTHONDONTWRITEBYTECODE=1 lifeops-api sh -c 'python -m pip install pytest && python -B -m pytest tests -q -p no:cacheprovider'
```

pytest was installed only inside the disposable validation container, without changing repository dependencies.

Result: **216 passed, 1 skipped, 0 failed**, with two existing warnings: SQLAlchemy nullable date annotation and Starlette/httpx. The only skip is the credential-gated smoke; the former time-dependent booking test runs deterministically. git diff --check passed.

The earlier real smoke, frontend human-in-the-loop flow and 2/5 → 5/5 chat reliability comparison were not rerun after this contract change. The five-call sample remains historical evidence, not a guarantee for the final contract.

## Feature Freeze

Implementation and validation are complete. No new backend features, Auditor Agent or reopening of architecture decisions are planned. Current priorities are visual polish, deployment, screenshots/GIF/demo evidence, presentation/LinkedIn and optional real-world usage. See AGENTS.md for operational invariants and the development log for chronology.
