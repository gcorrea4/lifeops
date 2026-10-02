# LifeOps — Week 1 Plan

## Top-Level Overview

**Goal:** Bootstrap the LifeOps project with a working vertical slice:
React → FastAPI → MySQL, powered by a deterministic availability engine.

**Scope:** MVP for Week 1 only. No authentication (hardcoded `user_id=1`).
No notifications, no AI, no calendar sync.

**Approach:**
1. Scaffold mono-repo folder structure (frontend + backend side by side).
2. Model and migrate the three core entities: `FixedBlock`, `Task`, `ScheduledSlot`.
3. Build CRUD endpoints for fixed blocks and tasks.
4. Implement the deterministic availability engine as a pure Python service.
5. Expose two engine endpoints: suggest slots + confirm booking.
6. Wire a minimal React UI that exercises the full flow.
7. Containerize with Docker Compose (API + MySQL).

**Out of scope (Week 1):**
- Authentication / JWT
- User registration
- Notifications / reminders
- AI suggestions
- Vercel / Azure deploy

---

## Architecture

```
lifeops/
├── backend/          # FastAPI application
│   ├── app/
│   │   ├── main.py
│   │   ├── database.py
│   │   ├── models/       # SQLAlchemy ORM models
│   │   ├── schemas/      # Pydantic request/response schemas
│   │   ├── routers/      # FastAPI routers (one per domain)
│   │   ├── services/     # Business logic (including engine)
│   │   └── core/         # Settings, constants
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/         # React + TypeScript + Vite
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   ├── services/     # Axios API calls
│   │   └── types/        # TypeScript interfaces mirroring Pydantic schemas
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
└── .env.exemple
```

---

## Entities

### FixedBlock
Represents an immovable time commitment (class, work shift, appointment).

| Field | Type | Notes |
|---|---|---|
| id | int PK | auto |
| user_id | int | hardcoded 1 for MVP |
| title | str | "Faculdade — Eng. Software" |
| recurrence_type | enum | `weekly` / `once` |
| weekday | int? | 0=Mon…6=Sun, null if `once` |
| date | date? | null if `weekly` |
| start_time | time | |
| end_time | time | |
| created_at | datetime | |

### Task
A unit of work with a required duration, not yet scheduled.

| Field | Type | Notes |
|---|---|---|
| id | int PK | auto |
| user_id | int | hardcoded 1 |
| title | str | |
| duration_minutes | int | e.g. 90 |
| deadline | date? | optional |
| priority | enum | `low` / `medium` / `high` |
| status | enum | `pending` / `scheduled` / `done` |
| created_at | datetime | |

### ScheduledSlot
A confirmed assignment of a task to a specific time window.

| Field | Type | Notes |
|---|---|---|
| id | int PK | auto |
| task_id | int FK → Task | |
| user_id | int | |
| start_datetime | datetime | chosen slot start |
| end_datetime | datetime | start + duration |
| created_at | datetime | |

---

## MVP Endpoints — Week 1

### Fixed Blocks
| Method | Path | Description |
|---|---|---|
| POST | `/blocks` | Create a fixed block |
| GET | `/blocks` | List all blocks for user |
| PUT | `/blocks/{id}` | Update a block |
| DELETE | `/blocks/{id}` | Delete a block |

### Tasks
| Method | Path | Description |
|---|---|---|
| POST | `/tasks` | Create a task |
| GET | `/tasks` | List tasks (filter by status) |
| PUT | `/tasks/{id}` | Update a task |
| DELETE | `/tasks/{id}` | Delete a task |

### Availability Engine
| Method | Path | Description |
|---|---|---|
| GET | `/engine/suggest?task_id={id}&from_date={date}&days={n}` | Returns ordered list of free slots that fit the task duration |
| POST | `/engine/book` | Body: `{task_id, start_datetime}` — creates ScheduledSlot and sets task status = scheduled |

### Scheduled Slots
| Method | Path | Description |
|---|---|---|
| GET | `/slots` | List all confirmed scheduled slots |
| DELETE | `/slots/{id}` | Unschedule a slot (resets task status to pending) |

---

## Deterministic Engine Logic (service layer)

```
suggest(task_id, from_date, days):
  1. Load task → get duration_minutes
  2. For each day in [from_date, from_date + days):
       a. Build occupied intervals from:
          - FixedBlocks (weekly matching weekday OR once matching date)
          - ScheduledSlots that overlap the day
       b. Sort occupied intervals, merge overlaps
       c. Compute free intervals within working_hours window (configurable, default 08:00–22:00)
       d. For each free interval >= duration_minutes → emit candidate slot
  3. Return list of {start_datetime, end_datetime, date} ordered by start
```

This is **pure Python, no ML, no randomness** — fully deterministic and testable.

---

## Overengineering Risks

| Risk | Why it's tempting | Mitigation |
|---|---|---|
| Adding JWT auth now | "We'll need it anyway" | Hardcode user_id=1, add auth in Week 2 |
| Generic recurrence engine (rrule) | Covers all edge cases | Weekly + once covers 95% of real use; avoid over-abstracting |
| Event sourcing / CQRS | Sounds robust | Simple CRUD + one service is enough for MVP |
| Celery / background tasks | For reminders later | No async jobs in Week 1 |
| Frontend state management (Redux/Zustand) | "App will grow" | React useState/useContext is sufficient for Week 1 |
| Abstract repository pattern | Testability | SQLAlchemy session passed directly; mock at DB level in tests |
| Multiple Docker services (Redis, Nginx) | Production-ready | Only API + MySQL in docker-compose for now |

---

## Sub-Tasks

---

### ST-1 — Project Scaffold
**Status:** [x] done

**Intent:** Create the mono-repo folder structure, base config files, and Docker Compose so all subsequent sub-tasks have a consistent foundation.

**Expected Outcomes:**
- `backend/` and `frontend/` directories exist with skeleton files.
- `docker-compose.yml` runs MySQL + FastAPI (even if API returns 200 on `/health`).
- `.env` loaded by both Docker and FastAPI via `python-dotenv`.

**Todo List:**
1. Create `backend/` with `requirements.txt`, `Dockerfile`, `app/main.py` (health route only).
2. Create `frontend/` with Vite scaffold (`npm create vite`), TypeScript template.
3. Write `docker-compose.yml` (services: `db`, `api`; volume for MySQL data).
4. Copy `.env.exemple` → `.env`, wire `DATABASE_URL` in `backend/app/core/settings.py`.
5. Verify `docker compose up` starts both services without errors.

**Relevant Context:**
- `.env.exemple` already defines `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`.
- MySQL service image: `mysql:8.0`.

---

### ST-2 — Database Models & Migrations
**Status:** [ ] pending

**Intent:** Define SQLAlchemy models for the three entities and run the initial migration so the schema exists in MySQL.

**Expected Outcomes:**
- Tables `fixed_blocks`, `tasks`, `scheduled_slots` exist in MySQL with correct columns.
- Alembic (or `Base.metadata.create_all`) applied cleanly.
- Models importable from `app/models/`.

**Todo List:**
1. Add SQLAlchemy + Alembic (or use `create_all` for MVP simplicity) to `requirements.txt`.
2. Create `app/database.py` — engine, SessionLocal, Base.
3. Create `app/models/fixed_block.py`, `task.py`, `scheduled_slot.py` per entity spec above.
4. Create enums (`RecurrenceType`, `Priority`, `TaskStatus`) in `app/models/enums.py`.
5. Run migration / `create_all` and confirm tables via MySQL client.

**Relevant Context:**
- Entity definitions are in the Entities section of this plan.
- `user_id` is not a FK (no users table in Week 1); just an int column.

---

### ST-3 — Pydantic Schemas
**Status:** [ ] pending

**Intent:** Define request/response schemas that FastAPI will use for validation and serialization. These should mirror the TypeScript types the frontend will use.

**Expected Outcomes:**
- `app/schemas/` contains `fixed_block.py`, `task.py`, `scheduled_slot.py`, `engine.py`.
- Each schema has `Create`, `Update`, and `Read` variants.
- `engine.py` contains `SlotSuggestion` and `BookRequest` schemas.

**Todo List:**
1. Create `FixedBlockCreate`, `FixedBlockUpdate`, `FixedBlockRead` in `schemas/fixed_block.py`.
2. Create `TaskCreate`, `TaskUpdate`, `TaskRead` in `schemas/task.py`.
3. Create `ScheduledSlotRead` in `schemas/scheduled_slot.py`.
4. Create `SlotSuggestion` (start, end, date) and `BookRequest` (task_id, start_datetime) in `schemas/engine.py`.
5. Enable `model_config = ConfigDict(from_attributes=True)` on all Read schemas.

---

### ST-4 — CRUD Routers
**Status:** [ ] pending

**Intent:** Implement the REST endpoints for fixed blocks, tasks, and scheduled slots.

**Expected Outcomes:**
- All endpoints listed in the "Fixed Blocks", "Tasks", and "Scheduled Slots" sections respond correctly.
- Tested manually via Swagger UI (`/docs`).

**Todo List:**
1. Create `app/routers/blocks.py` — 4 endpoints for FixedBlock CRUD.
2. Create `app/routers/tasks.py` — 4 endpoints for Task CRUD (GET accepts `?status=` filter).
3. Create `app/routers/slots.py` — GET list + DELETE (also resets task status to `pending`).
4. Register all routers in `app/main.py` with prefix `/api/v1`.
5. Write pytest smoke tests (create + read) for each router in `tests/`.

---

### ST-5 — Availability Engine Service
**Status:** [ ] pending

**Intent:** Implement the deterministic slot-suggestion algorithm as a pure Python service, fully unit-testable without a running database.

**Expected Outcomes:**
- `app/services/engine.py` contains `suggest_slots(task, blocks, existing_slots, from_date, days, working_hours)`.
- Function is pure (no DB calls inside) — DB queries happen in the router, data passed as arguments.
- At least 5 pytest unit tests covering: no blocks, full day blocked, partial overlap, multi-day, deadline filtering.

**Todo List:**
1. Create `app/services/engine.py` with `suggest_slots` function per the logic spec above.
2. Define `WorkingHours` config (default 08:00–22:00) in `app/core/settings.py`.
3. Create `app/routers/engine.py` — GET `/engine/suggest` + POST `/engine/book`.
4. In the suggest router: load task + blocks + slots from DB, call pure service, return list.
5. In the book router: validate slot is still free, create `ScheduledSlot`, set task status = `scheduled`.
6. Write unit tests for `suggest_slots` in `tests/test_engine.py` (no DB dependency).

---

### ST-6 — React Frontend (Minimal)
**Status:** [ ] pending

**Intent:** Build a minimal React UI that exercises the full Week 1 flow end-to-end.

**Expected Outcomes:**
- User can create a fixed block.
- User can create a task.
- User can request slot suggestions for a task and see the list.
- User can confirm a slot — it appears in the scheduled slots view.

**Todo List:**
1. Create Axios service layer in `frontend/src/services/api.ts` mirroring all MVP endpoints.
2. Create TypeScript interfaces in `frontend/src/types/` matching Read schemas.
3. Build `BlocksPage` — form to create + list of fixed blocks.
4. Build `TasksPage` — form to create + list of tasks with status badge.
5. Build `SuggestPage` — task picker, date range input, slot suggestion list with confirm button.
6. Add minimal routing (`react-router-dom`) with a sidebar nav.

---

### ST-7 — Docker Compose Integration
**Status:** [ ] pending

**Intent:** Ensure the full stack (MySQL + FastAPI + React dev server) runs with a single command.

**Expected Outcomes:**
- `docker compose up` starts all services.
- Frontend dev server proxies `/api` to FastAPI.
- MySQL data persists across restarts via a named volume.

**Todo List:**
1. Add `frontend` service to `docker-compose.yml` (runs `npm run dev` with port 5173 exposed).
2. Configure Vite proxy in `vite.config.ts` to forward `/api` → `http://api:8000`.
3. Add `healthcheck` on the `db` service; make `api` depend on it.
4. Document `docker compose up --build` in `readme.md`.
