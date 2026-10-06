# watsonx Validation Plan

## Overview

The goal is to validate that the existing `WatsonxProvider` works correctly with a real
IBM watsonx / Granite call. All infrastructure is already in place:

- `WatsonxProvider` in `backend/app/ai/provider.py` is fully implemented.
- `ibm-watsonx-ai` is already in `requirements.txt`.
- All credentials are read from environment variables via `settings`.
- `get_provider()` switches to `WatsonxProvider` when `AI_PROVIDER=watsonx`.

The plan requires **three small, focused changes**:

1. Verify and fix the `generate_text()` return value handling (the SDK may return a `dict`
   instead of a plain `str` in some versions; add a safe extraction guard).
2. Add a single integration smoke-test that is skipped when credentials are absent.
3. Update `.env.example` with the correct variable names (currently named `.env.exemple`).

No architecture changes. No new agents. No new routes.

---

## Sub-Tasks

---

### ST-9-A — Harden generate_text response extraction

**Status:** `[x] done`

**Intent**

`ibm-watsonx-ai >= 1.x` `ModelInference.generate_text()` returns a plain `str`.
Some SDK versions or call configurations may return a `dict` with a `"generated_text"` key
instead. A one-line guard inside `WatsonxProvider.complete()` ensures `complete()` always
returns a `str`, regardless of SDK version, so `PlannerAgent._parse_response()` never
receives unexpected input.

**Expected Outcomes**

- `WatsonxProvider.complete()` always returns `str`.
- If the SDK returns a `dict`, the `"generated_text"` field is extracted.
- If neither a `str` nor a recognisable `dict` arrives, a `ProviderError` is raised
  (which triggers the existing deterministic fallback).
- Existing tests remain green.

**Todo List**

1. Read the current `complete()` method in `backend/app/ai/provider.py`.
2. After `response = model.generate_text(prompt=prompt)`, add:
   ```python
   if isinstance(response, dict):
       response = response.get("generated_text", "")
   if not isinstance(response, str):
       raise ProviderError(f"Unexpected response type: {type(response)}")
   ```
3. Run `pytest backend/tests/` to confirm no regressions.

**Relevant Context**

- File: `backend/app/ai/provider.py`, `WatsonxProvider.complete()`, lines 82–97.
- The `PlannerAgent._parse_response()` in `backend/app/ai/agent.py` expects a `str`.

---

### ST-9-B — Add a credential-gated smoke test for WatsonxProvider

**Status:** `[x] done`

**Intent**

Add a single pytest test that:

- Is automatically **skipped** when `WATSONX_API_KEY` is not set (safe in CI).
- Calls `WatsonxProvider.complete()` with a minimal prompt when credentials are present.
- Asserts the result is a non-empty `str`.
- Does not assert specific JSON structure — this is a connectivity smoke test, not a
  PlannerAgent test.

This test acts as the manual validation gate before enabling `AI_PROVIDER=watsonx` in any
deployed environment.

**Expected Outcomes**

- `backend/tests/test_watsonx_provider.py` exists with one test function.
- Running `pytest` without credentials: 1 skip, no failures.
- Running `pytest` with real credentials exported: the test passes and prints the raw response.

**Todo List**

1. Create `backend/tests/test_watsonx_provider.py`.
2. Use `pytest.importorskip` or `pytest.mark.skipif` on `settings.WATSONX_API_KEY == ""`.
3. Instantiate `WatsonxProvider()` and call `.complete("Return the word HELLO as JSON: {\"word\": \"HELLO\"}")`.
4. Assert `isinstance(result, str)` and `len(result) > 0`.
5. Run `pytest backend/tests/test_watsonx_provider.py -v` to confirm the skip behaviour.

**Relevant Context**

- File to create: `backend/tests/test_watsonx_provider.py`.
- Settings file: `backend/app/core/settings.py` — `WATSONX_API_KEY` defaults to `""`.
- Provider: `backend/app/ai/provider.py`, `WatsonxProvider`.
- Existing pattern reference: `backend/tests/test_planner_agent.py`.

---

### ST-9-C — Fix .env.example filename and add missing variable documentation

**Status:** `[x] done`

**Intent**

The current template is named `.env.exemple` (typo). Rename it to `.env.example` (standard
convention) and ensure all five watsonx variables are present with inline comments.

**Expected Outcomes**

- `.env.example` exists at the project root with the correct filename.
- All five variables are documented: `AI_PROVIDER`, `WATSONX_API_KEY`, `WATSONX_PROJECT_ID`,
  `WATSONX_URL`, `WATSONX_MODEL_ID`.
- The old `.env.exemple` file is removed (or renamed).

**Todo List**

1. Read the current `.env.exemple` content.
2. Create `.env.example` with corrected content (all five watsonx variables with comments).
3. Delete `.env.exemple`.

**Relevant Context**

- Current file: `.env.exemple` at workspace root.
- Settings: `backend/app/core/settings.py` — the five `WATSONX_*` fields.

---

## Files Changed

| File | Action |
|---|---|
| `backend/app/ai/provider.py` | Modify — add response-type guard in `complete()` |
| `backend/tests/test_watsonx_provider.py` | Create — credential-gated smoke test |
| `.env.example` | Create — corrected filename with all watsonx variables |
| `.env.exemple` | Delete — typo filename |
