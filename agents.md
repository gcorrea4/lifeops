# LifeOps Project Context

## Project Goal

LifeOps is an auditable decision-support application that helps users organize personal tasks around fixed commitments such as university, work, travel time, and other events.

The system is intentionally divided into two layers:

1. deterministic scheduling and business constraints;
2. an AI recommendation and decision layer.

Deterministic rules always have priority over AI recommendations.

AI must never override hard scheduling constraints.

---

## Current Status

### ST-1 — Project Scaffold

Completed.

Implemented:

- React + TypeScript + Vite scaffold;
- FastAPI scaffold;
- MySQL via Docker Compose;
- GET /health;
- Docker networking;
- MySQL healthcheck.

### ST-2 — Database Models

Completed.

Implemented:

- SQLAlchemy setup;
- fixed_blocks;
- tasks;
- scheduled_slots;
- weekly and one-off recurrence;
- overnight blocks using spans_next_day;
- one ScheduledSlot maximum per Task;
- FK cascade;
- database constraints and indexes.

### ST-3 — Pydantic Schemas

Completed.

Implemented:

- FixedBlockCreate;
- FixedBlockUpdate;
- FixedBlockRead;
- TaskCreate;
- TaskUpdate;
- TaskRead;
- ScheduledSlotRead;
- SlotSuggestion;
- BookRequest.

Architecture decision:

Pydantic validates request-local rules only.

Rules that require persisted state are handled by the application layer after combining the database record with the incoming PATCH payload.

### ST-4 — CRUD Routers & Application Rules

Completed.

Implemented:

- FixedBlock CRUD;
- Task CRUD;
- ScheduledSlot read/delete endpoints;
- PATCH merge logic;
- recurrence validation after merge;
- spans_next_day calculation;
- conditional deadline validation;
- consistent HTTP errors;
- atomic ScheduledSlot deletion + Task status reset.

### ST-5 — Deterministic Availability Engine

Completed.

Implemented:

- GET /api/v1/engine/suggest;
- POST /api/v1/engine/book;
- configurable work window;
- default 7-day lookahead;
- maximum 10 suggestions;
- optional from_date;
- past from_date rejection;
- deadline enforcement;
- overnight FixedBlock handling;
- previous-day overnight occupancy;
- ScheduledSlot conflict detection;
- merge of overlapping and adjacent intervals;
- free interval calculation;
- duration filtering;
- booking-time conflict revalidation;
- atomic slot creation + Task status update.

Current test suite:


114 passed
0 failed
1 skipped

The skipped test is time-dependent and is tracked as technical debt.
Week 1 Status
Week 1 MVP is complete.
The application now supports:
React
-> FastAPI
-> MySQL
-> deterministic availability engine
-> slot suggestions
-> user confirmation / booking

No AI was used for hard scheduling decisions.
Current Next Phase
Week 2 — AI Decision Layer.
The AI layer must consume only slots that have already been validated by the deterministic engine.
The AI layer must not create availability or bypass scheduling constraints.
Week 2 Goal
Add explainable AI recommendations on top of the deterministic scheduling engine.
Target flow:
Deterministic Engine
        ↓
Valid Slots
        ↓
Planner Agent
        ↓
Recommendation
        ↓
Explanation
        ↓
Human Approval / Rejection
        ↓
Audit Trail

Approved Stack
Frontend
- React
- TypeScript
- Vite
Backend
- Python
- FastAPI
Database
- MySQL 8
- SQLAlchemy
Validation
- Pydantic
Testing
- pytest
- FastAPI TestClient
- SQLite in-memory database for isolated tests
Containers
- Docker
- Docker Compose
Planned Deployment
- Vercel
- Azure App Service
- Azure Database for MySQL
AI
Planned primary provider:
- IBM watsonx
- IBM Granite models
Possible fallback provider only if explicitly approved:
- Gemini
Agentic Development
- IBM Bob
Architecture Principles
- Keep the architecture simple.
- Avoid premature microservices.
- Avoid unnecessary abstractions.
- Do not introduce new frameworks without justification.
- Prefer pure functions for deterministic engine logic.
- Prefer readable code over clever abstractions.
- Business constraints must remain deterministic.
- AI must never override hard scheduling constraints.
- AI must receive only valid deterministic options.
- Users remain in control of final scheduling decisions.
- AI recommendations must be auditable.
- AI outputs should be structured.
- Do not store hidden chain-of-thought.
- Store concise decision explanations instead.
- Derived domain fields are computed server-side.
- Credentials must come from environment variables.
- Never commit secrets.
- Do not silently change approved architecture.
- Do not expand a sub-task beyond its approved scope without explicit approval.
Current Domain Rules
User
- No authentication yet.
- Temporary user_id = 1.
FixedBlock
FixedBlocks represent unavailable time.
Supported recurrence types:
weekly
once

Rules:
- weekly requires weekday;
- weekly forbids date;
- once requires date;
- once forbids weekday;
- weekday range is 0–6;
- start_time == end_time is invalid;
- blocks may cross midnight;
- spans_next_day is derived server-side;
- spans_next_day = end_time < start_time.
Task
Tasks represent work that should be scheduled.
Rules:
- duration_minutes must be greater than zero;
- deadline is optional;
- new deadline values cannot be explicitly set in the past;
- existing tasks may naturally become overdue;
- new tasks start as pending;
- TaskUpdate does not expose status.
Current statuses:
pending
scheduled
done

ScheduledSlot
ScheduledSlot represents a confirmed task allocation.
Rules:
- one Task may have at most one ScheduledSlot;
- generic ScheduledSlot creation is not exposed;
- creation happens through POST /engine/book;
- deleting a ScheduledSlot resets the related Task to pending;
- status reset and slot deletion must happen atomically.
Deterministic Engine Rules
The deterministic engine is authoritative for hard constraints.
It must remain independent from AI.
Suggest
GET /api/v1/engine/suggest:
1. loads the Task;
2. requires Task.status == pending;
3. uses configurable work window;
4. uses default 7-day lookahead;
5. accepts optional from_date;
6. rejects past from_date;
7. collects relevant FixedBlocks;
8. includes overnight occupancy from the previous day;
9. collects ScheduledSlots;
10. normalizes intervals;
11. merges overlapping and adjacent intervals;
12. computes free intervals;
13. filters by duration;
14. respects deadline;
15. returns at most 10 suggestions ordered by start_datetime ascending.
Deadline
A task must start and finish within the configured working window of the deadline date.
Inclusive boundary:
end_datetime <= datetime.combine(task.deadline, WORK_END)

A task ending exactly at WORK_END on the deadline date is valid.
Booking
POST /api/v1/engine/book must always revalidate current availability.
It must never trust a previously generated suggestion.
Expected flow:
load Task
↓
validate pending
↓
compute end_datetime
↓
validate deadline
↓
check FixedBlock collision
↓
check ScheduledSlot collision
↓
create ScheduledSlot
↓
Task.status = scheduled
↓
single atomic commit

Week 2 AI Rules
The AI layer must not decide whether a slot is valid.
Validity belongs exclusively to the deterministic engine.
The AI layer may:
- rank valid slots;
- recommend one of the valid slots;
- explain why it recommends a slot;
- consider Task priority;
- consider deadline proximity;
- consider user feedback;
- compare multiple valid options.
The AI layer must not:
- invent unavailable slots;
- bypass FixedBlocks;
- bypass ScheduledSlots;
- schedule outside the work window;
- ignore deadlines;
- directly mutate Task.status;
- book without deterministic revalidation.
Explainability Rules
Do not store hidden chain-of-thought.
Store structured explanations instead.
Example:
{
  "recommended_slot": "2026-10-05T14:00:00",
  "reason_codes": [
    "DEADLINE_CLOSE",
    "HIGH_PRIORITY",
    "EARLY_VALID_SLOT"
  ],
  "explanation": "This slot was recommended because the task has a close deadline and this is one of the earliest valid windows."
}

Future AI responses should prefer structured JSON-like outputs over free-form prose.
Human-in-the-Loop Rules
AI recommendations are suggestions.
The user must be able to:
Approve
Modify
Reject

Booking must only occur after explicit user confirmation.
Future feedback should be stored for auditability and later analysis.
Planned Auditability
Future AI decisions should record:
- decision id;
- timestamp;
- task id;
- model/provider;
- candidate slots;
- recommended slot;
- reason codes;
- concise explanation;
- user action;
- final selected slot.
Do not store sensitive secrets or hidden model reasoning.
Error Handling Principles
Use standard FastAPI errors.
Examples:
404
resource not found

409
state conflict

422
invalid business input

Do not create a custom exception framework unless there is a real need.
Testing Principles
Tests must not connect to the real development MySQL database.
Current integration tests use:
- SQLite in-memory;
- StaticPool;
- check_same_thread=False;
- foreign_keys enabled;
- get_db dependency override.
Future AI tests should:
- mock external AI providers;
- never require real watsonx credentials in unit tests;
- validate structured output;
- validate invalid AI output handling;
- verify deterministic constraints remain authoritative;
- verify booking still revalidates availability.
Do not reduce existing test coverage.
Current Known Technical Debt
SQLAlchemy warning
SQLAlchemy 2.1 emits one deprecation warning related to the nullable date annotation in:
models/fixed_block.py

It does not currently affect functionality.
Time-dependent test
One deadline-related booking test is currently skipped depending on the current time of day.
Future cleanup should make time-based tests deterministic by injecting or freezing the clock instead of relying directly on the real current time.
Do not modify these items unless:
- they cause a functional issue; or
- a dedicated cleanup task is approved.
Development Workflow
For every major sub-task:
1. read AGENTS.md;
2. read the current plan file;
3. inspect only relevant code;
4. propose a plan;
5. identify files to create or modify;
6. identify business rules affected;
7. identify tests required;
8. wait for user approval;
9. implement only approved scope;
10. run relevant tests;
11. report warnings and errors;
12. do not silently expand scope;
13. update documentation after completion.
Preferred workflow with IBM Bob:
Plan
↓
Human review
↓
Agent
↓
Tests
↓
Validation
↓
Commit

Do Not Implement Yet
Until explicitly approved, do not add:
- authentication;
- OAuth;
- Redis;
- Celery;
- background jobs;
- microservices;
- Kubernetes;
- OpenShift;
- production UI redesign;
- additional AI providers;
- autonomous booking without user confirmation.
Those belong to later phases or require explicit approval.

Esse é o momento certo para atualizar, porque agora o `AGENTS.md` deixa de ser “guia da Semana 1” e passa a preparar o Bob para a fase que realmente diferencia o projeto: **IA em cima de uma base determinística já validada**.