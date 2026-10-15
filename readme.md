# LifeOps

**Live demo: https://boblifeops.vercel.app** (English and Portuguese, light and dark theme)

LifeOps helps organize personal tasks around fixed commitments such as university, work, travel, and overnight events. It addresses the difficulty of finding realistic time for tasks with different durations, priorities, and deadlines.

> AI-assisted, human-controlled and auditable by design. A deterministic engine decides what is valid, an AI suggests one option, and the person decides.

![LifeOps with the Bob mascot](docs/screenshots/00-bob.gif)

## Screenshots

| Tasks and fixed commitments | Recommendation with explanation |
|---|---|
| ![Tasks and fixed commitments](docs/screenshots/01-tasks-and-commitments.png) | ![Recommendation in Portuguese with the model explanation and reason code](docs/screenshots/02-recommendation.png) |

![Decision recorded; booking is a separate explicit action](docs/screenshots/03-decision.png)

The captures show the Portuguese interface in the dark theme: the model's explanation, the backend-derived reason code, the original candidates, and the recorded decision with the separate "book" step.

## How it works

LifeOps combines a deterministic availability engine with an AI recommendation layer. The engine computes candidate slots from scheduling constraints, excludes starts at or before the current time, and enforces the configured daily work window when booking. The model returns only a candidate ID and a concise explanation; the backend derives reason codes deterministically. AI never creates availability or invents scheduling datetimes.

```
Commitments + tasks + existing slots + rules
        -> deterministic availability engine -> valid candidate slots
        -> PlannerAgent -> IBM watsonx picks a candidate_id
        -> backend guards + derived reason codes -> persisted recommendation (audit)
        -> human decision: APPROVED / MODIFIED / REJECTED (task stays pending)
        -> explicit booking, revalidated against current state -> scheduled slot
```

Recommendations, human decisions, and booking are separate actions. Approving a recommendation leaves the task pending. An explicit booking request revalidates current conflicts and deadlines before creating a scheduled slot. If the model fails or answers invalidly, the system falls back to the first valid slot and says so.

The audit trail records the provider, model, original candidates, recommendation, explanation, fallback status, and human decision. Raw model output and hidden chain-of-thought are not stored. The free-text explanation is written by the model and can be imprecise; the reason codes are computed by the system.

## Stack

- Frontend: React, TypeScript, Vite, plain responsive CSS, EN/PT interface, light/dark theme. Layout adapted from the Massively template by HTML5 UP.
- Backend: Python, FastAPI, Pydantic, SQLAlchemy.
- Database: MySQL 8 (Docker Compose locally, Azure Database for MySQL in the demo).
- AI: IBM watsonx through the IBM watsonx AI SDK (`meta-llama/llama-3-3-70b-instruct`).
- Tests: pytest with isolated SQLite integration tests.
- Hosting of the demo: Vercel (frontend), Azure App Service (API), Azure Database for MySQL.

IBM Bob has supported planning and implementation across the software development lifecycle, with human review of plans before Agent implementation. Codex and Claude Code have also assisted with implementation, validation and documentation; no single tool did all of the work.

## Run locally

```bash
cp .env.example .env          # fill the database values; leave AI_PROVIDER=mock to run without credentials
docker compose up -d          # MySQL and the API on http://localhost:8000
cd frontend && npm install && npm run dev   # http://localhost:5173 (proxies /api to the API)
```

With `AI_PROVIDER=mock` every recommendation uses the deterministic fallback. Set `AI_PROVIDER=watsonx` and the `WATSONX_*` values in `.env` for real recommendations. Run the tests with `cd backend && python -m pytest`.

## About the public demo

- There is no login. Each browser gets a random identifier and only sees its own data. This separates data for a demo; it is **not** authentication.
- A visitor's data is deleted 24 hours after it is created, and each visitor can request up to 10 recommendations per day. There are also global limits on AI calls and on items per visitor to protect the free watsonx quota.
- The API runs on a free App Service plan: the first request after a period of inactivity can take about 20 seconds.
- Dates and times are naive local values on purpose; there is no time-zone redesign.

## Status and validation

The MVP is feature-frozen. Backend suite: **255 passed, 1 skipped** (the skip is the live watsonx smoke test, which needs credentials and passed separately). Frontend build and lint pass. The full flow (task, commitments, real watsonx recommendation, approve/modify/reject, explicit booking, conflict handling, daily limit) was exercised on the public site in both languages, with all test data removed afterwards.

Real watsonx calls were validated with the final two-field contract. The model used is a non-IBM model served through IBM watsonx, because the Lite/Sydney runtime did not offer IBM Granite; Granite remains a future validation target. Reliability figures from small samples are not guarantees.

Known limits: no authentication, a single shared database schema without migrations, no automated frontend interaction tests, naive datetimes, and free-text explanations that may be wrong.

Possible next steps beyond this MVP: real authentication, calendar integration, persistent data without expiry, and validating an IBM Granite model.

See [agent context](agents.md), [development log](BOB-DEVELOPMENT-LOG.md), [watsonx validation record](watsonx-validation-plan.md), [demo validation report](demo-validation-report.md) and [test report](test-report.md) for details.
