
# LifeOps Project Context

## Project Goal

LifeOps is an auditable decision-support application that helps users organize personal tasks around fixed commitments such as university, work, travel time, and other events.

The system is intentionally divided into two layers:

1. deterministic scheduling and business constraints;
2. an AI decision layer planned for later phases.

Deterministic rules always have priority over AI recommendations.

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

Tests after ST-3:

```txt
22 passed

ST-4 — CRUD Routers & Application Rules
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
Current test suite:
58 passed
0 failed

Current Next Step
ST-5 — Deterministic Availability Engine.
Do not start AI implementation during ST-5.
Week 1 Goal
Build a fully functional MVP without AI.
Target flow:
React
-> FastAPI
-> MySQL
-> deterministic availability engine
-> slot suggestions
-> user confirmation

AI is intentionally excluded from Week 1.
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
Future AI
- IBM watsonx
- Granite models
Architecture Principles
- Keep the architecture simple.
- Avoid premature microservices.
- Avoid unnecessary abstractions.
- Do not introduce new frameworks without justification.
- Prefer pure functions for deterministic engine logic.
- Prefer readable code over clever abstractions.
- Business constraints must remain deterministic.
- AI must never override hard scheduling constraints.
- Users remain in control of final scheduling decisions.
- Future AI recommendations must be auditable.
- Derived domain fields are computed server-side.
- Partial PATCH requests must be merged with persisted state before complete-state validation.
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
For PATCH:
existing state
+
incoming fields
↓
candidate state
↓
validate candidate
↓
calculate derived fields
↓
persist

Never validate complete-state rules using only a partial PATCH payload.
Task
Tasks represent work that should be scheduled.
Rules:
- duration_minutes must be greater than zero;
- deadline is optional;
- new deadline values cannot be explicitly set in the past;
- existing tasks may naturally become overdue;
- new tasks start as pending;
- TaskUpdate does not expose status.
Status transitions must happen through domain actions.
Current statuses:
pending
scheduled
done

ScheduledSlot
ScheduledSlot represents a confirmed task allocation.
Rules:
- one Task may have at most one ScheduledSlot in Week 1;
- generic ScheduledSlot creation is not exposed;
- creation will happen through POST /engine/book;
- deleting a ScheduledSlot resets the related Task to pending;
- status reset and slot deletion must happen atomically.
ST-5 Scope
ST-5 must implement the deterministic scheduling engine.
Expected endpoints:
GET  /api/v1/engine/suggest
POST /api/v1/engine/book

ST-5 Engine Rules
Suggest
The suggest flow must:
1. load the Task by task_id and user_id=1;
2. return 404 if task does not exist;
3. reject tasks that are not pending;
4. use default lookahead of 7 days;
5. use configurable daily working window;
6. collect FixedBlocks relevant to each day;
7. collect existing ScheduledSlots;
8. normalize all occupied intervals;
9. include previous-day overnight FixedBlocks;
10. merge overlapping occupied intervals;
11. compute free intervals;
12. keep only intervals that fit task.duration_minutes;
13. respect the Task deadline;
14. return candidate slots ordered deterministically.
The engine must not use AI.
Overnight FixedBlocks
Example:
Monday
18:00 → 06:00
spans_next_day = true

The occupied intervals are:
Monday   18:00 → midnight
Tuesday  midnight → 06:00

When calculating availability for day D, the engine must inspect:
FixedBlocks matching D
+
overnight FixedBlocks from D-1

Interval Logic
Prefer pure functions.
Suggested conceptual flow:
occupied intervals
↓
sort by start
↓
merge overlaps
↓
calculate gaps
↓
filter by required duration
↓
candidate slots

Avoid unnecessary classes or scheduling frameworks.
Deadline Behavior
A Task deadline limits candidate generation.
Do not suggest a slot after the deadline.
The exact interpretation of whether the task must finish before the end of the deadline date must be explicit in the ST-5 plan before implementation.
Do not silently choose semantics.
Booking
POST /engine/book must never trust a previous suggestion.
It must revalidate availability at booking time.
Expected flow:
load Task
↓
validate pending
↓
calculate end_datetime
↓
check deadline
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

The database UNIQUE constraint on ScheduledSlot.task_id remains a final safety guard.
Error Handling Principles
Use standard FastAPI errors.
Examples:
404
resource not found

409
state conflict / already scheduled

422
invalid business input

Do not create a custom exception framework unless a real need appears.
Testing Principles
Tests must not connect to the real development MySQL database.
Router/integration tests currently use:
- SQLite in-memory;
- StaticPool;
- check_same_thread=False;
- foreign_keys enabled;
- get_db dependency override.
ST-5 should include:
- pure engine unit tests;
- engine router integration tests;
- overnight cases;
- overlapping intervals;
- adjacent intervals;
- full-day occupancy;
- empty schedule;
- task exactly fitting a free interval;
- deadline boundaries;
- booking conflict revalidation;
- task already scheduled;
- duplicate booking protection.
Do not reduce existing test coverage.
Current Known Technical Debt
SQLAlchemy 2.1 currently emits one deprecation warning related to the nullable date annotation in:
models/fixed_block.py

The warning does not affect current functionality.
Do not modify it unless:
- it causes a functional issue; or
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
- AI;
- watsonx integration;
- Granite integration;
- authentication;
- OAuth;
- Redis;
- Celery;
- background jobs;
- microservices;
- Kubernetes;
- OpenShift;
- production UI redesign.
Those belong to later phases.
```
