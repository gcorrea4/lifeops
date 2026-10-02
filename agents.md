
# LifeOps Project Context

## Project Goal

LifeOps is an auditable decision-support application that helps organize personal tasks around fixed commitments such as university, work, travel time and other events.

The system should combine deterministic scheduling rules with an AI decision layer in later phases.

## Current Status

ST-1: completed

- React + TypeScript + Vite scaffold
- FastAPI scaffold
- MySQL via Docker Compose
- GET /health working

ST-2: completed

- SQLAlchemy database setup
- fixed_blocks table
- tasks table
- scheduled_slots table
- hybrid recurring/one-off blocks
- overnight blocks supported with spans_next_day
- one scheduled slot per task
- MySQL healthcheck and Docker networking validated

## Week 1 Goal

Build a fully functional MVP without AI.

Target flow:
React
-> FastAPI
-> MySQL
-> deterministic availability engine
-> slot suggestions
-> user confirmation

## Approved Stack

Frontend:

- React
- TypeScript
- Vite

Backend:

- Python
- FastAPI

Database:

- MySQL 8
- SQLAlchemy

Validation:

- Pydantic

Testing:

- pytest

Containers:

- Docker
- Docker Compose

Deployment planned:

- Vercel
- Azure App Service
- Azure Database for MySQL

## Architecture Principles

- Keep architecture simple.
- Avoid premature microservices.
- Do not introduce new frameworks without justification.
- Business constraints must be deterministic.
- AI must never override hard scheduling constraints.
- User remains in control of final scheduling decisions.
- All future AI recommendations must be auditable.
- Prefer readable code over clever abstractions.
- Credentials must come from environment variables.
- Never commit secrets.

## Week 1 Domain Rules

- No authentication yet.
- Temporary user_id = 1.
- Fixed blocks may be:
  - weekly recurring
  - one-off
- Fixed blocks may cross midnight.
- Tasks have duration, priority, optional deadline and status.
- A task may have at most one ScheduledSlot in Week 1.
- Scheduling suggestions are read-only until user confirms a slot.

## Current Next Step

ST-3 — Pydantic Schemas.

Do not implement CRUD routers or the availability engine during ST-3.

## Development Workflow

For each major sub-task:

1. inspect only relevant files;
2. propose a plan;
3. identify files to change;
4. wait for approval;
5. implement only the approved sub-task;
6. test the result;
7. report warnings/errors;
8. do not silently change approved architecture.
