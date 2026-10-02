
# LifeOps Project Context

## Project Goal

LifeOps is an auditable decision-support application that helps users organize personal tasks around fixed commitments such as university, work, travel time, and other events.

The system combines deterministic scheduling rules with an AI decision layer planned for later phases.

## Current Status

### ST-1 — Project Scaffold

Completed.

- React + TypeScript + Vite scaffold
- FastAPI scaffold
- MySQL via Docker Compose
- GET /health working
- Docker networking validated

### ST-2 — Database Models

Completed.

Implemented:

- SQLAlchemy database setup
- fixed_blocks table
- tasks table
- scheduled_slots table
- hybrid recurring/one-off fixed blocks
- overnight blocks supported through spans_next_day
- one scheduled slot per task
- MySQL healthcheck
- Docker service discovery using db as database host

### ST-3 — Pydantic Schemas

Completed.

Implemented:

- FixedBlockCreate
- FixedBlockUpdate
- FixedBlockRead
- TaskCreate
- TaskUpdate
- TaskRead
- ScheduledSlotRead
- SlotSuggestion
- BookRequest

Validation tests:

- 22 tests passing

Important architectural decision:
Pydantic validates request-local rules only.

Rules that require the complete persisted state are handled by the application layer after combining the database record with the incoming PATCH payload.

Deferred to ST-4:

- recurrence mutual exclusivity after PATCH merge
- spans_next_day calculation after PATCH merge
- application-level domain validation

## Week 1 Goal

Build a fully functional MVP without AI.

Target flow:

React
-> FastAPI
-> MySQL
-> deterministic availability engine
-> slot suggestions
-> user confirmation

AI is intentionally excluded from Week 1.

## Approved Stack

### Frontend

- React
- TypeScript
- Vite

### Backend

- Python
- FastAPI

### Database

- MySQL 8
- SQLAlchemy

### Validation

- Pydantic

### Testing

- pytest

### Containers

- Docker
- Docker Compose

### Planned Deployment

- Vercel
- Azure App Service
- Azure Database for MySQL

## Architecture Principles

- Keep the architecture simple.
- Avoid premature microservices.
- Do not introduce new frameworks without justification.
- Business constraints must be deterministic.
- AI must never override hard scheduling constraints.
- User remains in control of final scheduling decisions.
- All future AI recommendations must be auditable.
- Prefer readable code over clever abstractions.
- Credentials must come from environment variables.
- Never commit secrets.
- Do not silently change approved architecture.
- Derived domain fields should be computed server-side.
- Partial PATCH requests must be merged with persisted state before complete-state business validation.

## Week 1 Domain Rules

### User

- No authentication yet.
- Temporary user_id = 1.

### FixedBlock

- May be weekly recurring or one-off.
- May cross midnight.
- start_time == end_time is invalid.
- spans_next_day is derived server-side.
- Weekly recurrence requires weekday and forbids date.
- One-off recurrence requires date and forbids weekday.

### Task

- Has title, duration, priority, optional deadline, and status.
- New tasks start as pending.
- Task status cannot be changed arbitrarily through TaskUpdate.

### ScheduledSlot

- A task may have at most one ScheduledSlot in Week 1.
- ScheduledSlot creation is not exposed as generic CRUD.
- Scheduling will happen through the engine booking flow.
- Deleting a scheduled slot should return the related task to pending.

## Current Next Step

ST-4 — CRUD Routers & Application Rules.

ST-4 scope:

- FixedBlock CRUD
- Task CRUD
- ScheduledSlot read/delete endpoints
- partial PATCH merge logic
- recurrence business-rule validation
- spans_next_day calculation
- consistent HTTP error handling

Do NOT implement yet:

- availability engine
- /engine/suggest
- /engine/book
- AI
- authentication
- production frontend design

## Development Workflow

For each major sub-task:

1. inspect only relevant files;
2. read AGENTS.md and the current sub-task plan;
3. propose a plan;
4. identify files to create or modify;
5. identify domain rules affected;
6. wait for approval;
7. implement only the approved scope;
8. run relevant tests;
9. report warnings and errors;
10. do not silently expand scope;
11. update documentation after completion.

## Current Known Technical Debt

- SQLAlchemy 2.1 emits a deprecation warning related to the current nullable date type annotation in fixed_block.py.
- It does not affect current functionality.
- Do not modify it unless it causes a functional problem or a dedicated cleanup task is approved.
