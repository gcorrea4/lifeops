# LifeOps

LifeOps helps organize personal tasks around fixed commitments such as university, work, travel, and overnight events. It addresses the difficulty of finding realistic time for tasks with different durations, priorities, and deadlines.

## How it works

LifeOps combines a deterministic availability engine with an AI recommendation layer. The engine computes candidate slots from scheduling constraints, excludes starts at or before the current time, and enforces the configured daily work window when booking. The PlannerAgent selects a candidate and supplies a concise explanation; AI never creates availability or invents scheduling datetimes.

Recommendations, human decisions, and booking are separate actions. Approving a recommendation leaves the task pending. An explicit booking request revalidates current conflicts and deadlines before creating a scheduled slot.

The audit trail records the provider, model, original candidates, recommendation, explanation, fallback status, and human decision. Raw model output and hidden chain-of-thought are not stored.

## Stack and development

- React, TypeScript, and Vite one-page frontend MVP.
- Python, FastAPI, Pydantic, SQLAlchemy, and MySQL 8 backend.
- Docker and Docker Compose.
- pytest with isolated SQLite integration tests.
- IBM watsonx through the IBM watsonx AI SDK.

IBM Bob has supported planning and implementation across the software development lifecycle, with human review of plans before Agent implementation. Codex has also assisted with frontend implementation, validation and documentation; Bob was not the only tool used.

## Current status

ST-1 through ST-9, including ST-8 cleanup, are complete. Backend CRUD, deterministic scheduling, PlannerAgent, recommendation and decision endpoints, audit persistence, and real watsonx integration are implemented. The frontend MVP is complete: create/list tasks and commitments, review recommendations and original candidates, approve/modify/reject, and explicitly book. Weekly, one-off and overnight commitments are supported. Deployment is planned; this is not a production design.

Recorded backend automated results: **186 passed, 1 skipped, 0 failed**. The only skip is the credential-gated live smoke when credentials are disabled; that smoke passed separately. Frontend TypeScript/Vite build and lint passed with no warnings.

Real IBM Cloud authentication and watsonx Runtime calls were validated using `meta-llama/llama-3-3-70b-instruct`. The provider now uses the chat API with JSON response format. A controlled five-call comparison improved from **2/5 valid structured responses and 3 fallbacks** to **5/5 valid responses and no fallbacks**. This small sample is not a reliability guarantee; explanation semantics still need attention.

Real end-to-end validation covered the earlier backend fallback flow and a later frontend flow with a structured watsonx response: modify an original candidate, record the decision while the task remains pending, then explicitly book and transition to scheduled. Rejection without booking and overnight commitment creation were also confirmed. IBM Granite remains a future validation target because the available Lite/Sydney runtime did not support the planned model.

See [agent context](agents.md), [watsonx validation record](watsonx-validation-plan.md), and [development log](BOB-DEVELOPMENT-LOG.md) for details.
