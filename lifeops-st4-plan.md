# ST-4 — CRUD Routers & Application Rules Plan

## Top-Level Overview

**Goal:** Implement the HTTP layer and application service layer for FixedBlock, Task, and
ScheduledSlot — without the availability engine.

**Scope:** New routers, new service modules, conftest + router tests.
Existing models, schemas, and database files are NOT modified except for
`app/main.py` (router registration only).

**Approach:**
- One router file per domain entity (blocks, tasks, slots).
- One service file per entity that owns mutation logic (fixed_block, task).
- Services operate on candidate dictionaries before mutating ORM objects.
- Routers delegate all business-rule checks to the service layer.
- Tests use an in-memory SQLite database via a shared conftest.

**Validation boundary (unchanged from ST-3):**

| Concern | Owner |
|---|---|
| Field format / range (weekday 0–6, duration > 0) | Pydantic |
| `start_time != end_time` on Create (both fields always present) | Pydantic |
| `deadline` not in the past on Create | Pydantic |
| Recurrence mutual exclusivity after merge | Service layer |
| `start_time != end_time` after merge | Service layer |
| `spans_next_day = end_time < start_time` after merge | Service layer |
| `deadline` not in the past — only when explicitly sent in PATCH | Service layer |
| Task status transitions | Engine actions only (ST-5) |

**Out of scope for ST-4:**
- Availability engine (`/engine/suggest`, `/engine/book`)
- AI, authentication, production frontend

---

## Sub-Tasks

---

### ST-4.1 — `services/fixed_block.py`
**Status:** [x] done

**Intent:**
Implement the three service functions that enforce application-level rules for FixedBlock.
These run on a candidate state (a plain dict) assembled from the merged DB record + patch payload,
so the ORM object is never mutated until all validations pass.

**Expected Outcomes:**
- `validate_recurrence(candidate)` raises `HTTPException 422` when mutual exclusivity is violated.
- `validate_time_range(candidate)` raises `HTTPException 422` when `start_time == end_time`.
- `compute_spans_next_day(candidate)` returns the correct boolean.
- `apply_patch(db_block, payload)` assembles a candidate dict, runs all three functions in order
  (recurrence → time_range → spans_next_day), then writes the validated values onto the ORM object.

**Mutation order inside `apply_patch`:**
```
1. Build candidate dict from db_block fields.
2. Overlay only the fields present in payload (exclude_unset=True).
3. Call validate_recurrence(candidate)     → HTTPException 422 on violation
4. Call validate_time_range(candidate)     → HTTPException 422 if start == end
5. candidate["spans_next_day"] = compute_spans_next_day(candidate)
6. Write all candidate values back onto db_block attributes.
7. Return db_block (mutated in-place).
```

**Todo List:**
1. Create `backend/app/services/__init__.py` (empty).
2. Create `backend/app/services/fixed_block.py`:
   - `validate_recurrence(candidate: dict) -> None`
     - `weekly` → weekday must be int (not None), date must be None.
     - `once` → date must be set (not None), weekday must be None.
     - Raise `HTTPException(status_code=422, detail="...")` on violation.
   - `validate_time_range(candidate: dict) -> None`
     - Raise `HTTPException(status_code=422, detail="start_time and end_time must not be equal")`
       if `candidate["start_time"] == candidate["end_time"]`.
   - `compute_spans_next_day(candidate: dict) -> bool`
     - Return `candidate["end_time"] < candidate["start_time"]`.
   - `apply_patch(db_block: FixedBlock, payload: FixedBlockUpdate) -> FixedBlock`
     - Follows the mutation order described above.

**Relevant Context:**
- `app/models/fixed_block.py` — `FixedBlock` ORM model
- `app/schemas/fixed_block.py` — `FixedBlockUpdate` (all fields Optional; `exclude_unset=True`
  gives only fields the client explicitly sent)
- `app/models/enums.py` — `RecurrenceType.weekly`, `RecurrenceType.once`
- The candidate dict approach ensures the ORM object is never in a partially-invalid state
  during validation, which avoids needing to roll back ORM attribute changes on failure.

---

### ST-4.2 — `services/task.py`
**Status:** [x] done

**Intent:**
Implement the service function for Task PATCH. The only application-level rule here is the
conditional deadline validation: a deadline explicitly sent in the PATCH must not be in the past.
A stored deadline that has already passed is not re-validated by PATCH (the task just exists as
overdue — that's intentional domain behaviour).

**Expected Outcomes:**
- `apply_patch(db_task, payload)` applies the payload fields to the ORM object.
- If `deadline` is present in the payload and the value is in the past, raises `HTTPException 422`.
- `status` is never set by this function.

**Todo List:**
1. Create `backend/app/services/task.py`:
   - `apply_patch(db_task: Task, payload: TaskUpdate) -> Task`
     - Build a candidate dict from the payload fields only (`exclude_unset=True`).
     - If `"deadline"` is in the candidate dict and `candidate["deadline"] < date.today()`,
       raise `HTTPException(status_code=422, detail="deadline must be today or in the future")`.
     - Apply the candidate fields onto `db_task` attributes.
     - Return `db_task`.

**Relevant Context:**
- `app/models/task.py` — `Task` ORM model
- `app/schemas/task.py` — `TaskUpdate` (all Optional; `status` absent)
- `deadline_not_in_the_past` already exists on `TaskCreate` in Pydantic — do NOT add it to
  `TaskUpdate`. The service handles the PATCH case to distinguish "client explicitly sent a new
  deadline" from "stored deadline is old".
- No candidate-dict round-trip for Task — only `deadline` requires conditional checking, so the
  simpler pattern (check then write) is sufficient.

---

### ST-4.3 — `routers/blocks.py`
**Status:** [x] done

**Intent:**
Implement the five FixedBlock endpoints. Business-rule validation is fully delegated to the
service layer. The router handles HTTP concerns only.

**Expected Outcomes:**
- `POST   /api/v1/blocks`          → 201, `FixedBlockRead`
- `GET    /api/v1/blocks`          → 200, `list[FixedBlockRead]`
- `GET    /api/v1/blocks/{id}`     → 200, `FixedBlockRead` or 404
- `PATCH  /api/v1/blocks/{id}`     → 200, `FixedBlockRead` or 404/422
- `DELETE /api/v1/blocks/{id}`     → 204 or 404

**Todo List:**
1. Create `backend/app/routers/__init__.py` (empty).
2. Create `backend/app/routers/blocks.py`:
   - `APIRouter(prefix="/blocks", tags=["blocks"])`
   - `POST /` — accepts `FixedBlockCreate`:
     - Inline creation logic (no separate service needed):
       build a candidate dict from the payload, call `validate_recurrence`, `validate_time_range`,
       `compute_spans_next_day`, then instantiate `FixedBlock(user_id=1, spans_next_day=..., **payload_dict)`.
     - `db.add(block); db.commit(); db.refresh(block)` → return 201.
   - `GET /` — query all blocks where `user_id=1`, return list.
   - `GET /{block_id}` — fetch by id + user_id=1, raise 404 if missing.
   - `PATCH /{block_id}` — fetch, call `fixed_block_service.apply_patch(block, payload)`,
     commit, return 200.
   - `DELETE /{block_id}` — fetch, `db.delete(block)`, commit, return 204.

**Relevant Context:**
- `app/services/fixed_block.py` (ST-4.1) — all business logic
- `app/schemas/fixed_block.py` — `FixedBlockCreate`, `FixedBlockUpdate`, `FixedBlockRead`
- `app/models/fixed_block.py` — `FixedBlock`
- `app/database.py` — `get_db` dependency
- Hardcode `user_id = 1` everywhere (no auth in Week 1).
- `FixedBlockCreate` already rejects `start_time == end_time` via Pydantic, so POST does not
  need to call `validate_time_range` explicitly — but calling it for consistency is acceptable.

---

### ST-4.4 — `routers/tasks.py`
**Status:** [x] done

**Intent:**
Implement the five Task endpoints. The `?status=` query parameter must filter results.
Status cannot be set via Create or Update.

**Expected Outcomes:**
- `POST   /api/v1/tasks`              → 201, `TaskRead` (status always `pending`)
- `GET    /api/v1/tasks`              → 200, `list[TaskRead]`
- `GET    /api/v1/tasks?status=X`     → 200, filtered list
- `GET    /api/v1/tasks/{id}`         → 200, `TaskRead` or 404
- `PATCH  /api/v1/tasks/{id}`         → 200, `TaskRead` or 404/422
- `DELETE /api/v1/tasks/{id}`         → 204 or 404

**Todo List:**
1. Create `backend/app/routers/tasks.py`:
   - `APIRouter(prefix="/tasks", tags=["tasks"])`
   - `POST /` — accepts `TaskCreate`:
     - Instantiate `Task(user_id=1, status=TaskStatus.pending, **payload.model_dump())`.
     - `db.add(task); db.commit(); db.refresh(task)` → return 201.
   - `GET /` — optional `status: Optional[TaskStatus] = Query(None)` param.
     - If provided, filter `where Task.status == status`.
     - Return list.
   - `GET /{task_id}` — fetch by id + user_id=1, raise 404 if missing.
   - `PATCH /{task_id}` — fetch, call `task_service.apply_patch(task, payload)`, commit, return 200.
   - `DELETE /{task_id}` — fetch, `db.delete(task)`, commit, return 204.

**Relevant Context:**
- `app/services/task.py` (ST-4.2)
- `app/schemas/task.py` — `TaskCreate`, `TaskUpdate`, `TaskRead`
- `app/models/task.py` — `Task`; `scheduled_slot` relationship with `CASCADE` on FK
- `TaskStatus` enum values: `pending`, `scheduled`, `done`
- When a Task is deleted, the FK `ondelete=CASCADE` removes the ScheduledSlot automatically —
  no explicit slot deletion needed in the task router.

---

### ST-4.5 — `routers/slots.py`
**Status:** [x] done

**Intent:**
Implement the three ScheduledSlot endpoints. The DELETE endpoint must atomically reset the
related task's status to `pending` before removing the slot. Both writes happen inside a single
transaction commit.

**Expected Outcomes:**
- `GET    /api/v1/slots`         → 200, `list[ScheduledSlotRead]`
- `GET    /api/v1/slots/{id}`    → 200, `ScheduledSlotRead` or 404
- `DELETE /api/v1/slots/{id}`    → 204 or 404; related task.status == `pending` after delete

**Todo List:**
1. Create `backend/app/routers/slots.py`:
   - `APIRouter(prefix="/slots", tags=["slots"])`
   - `GET /` — query all slots where `user_id=1`, return list.
   - `GET /{slot_id}` — fetch by id + user_id=1, raise 404 if missing.
   - `DELETE /{slot_id}`:
     - Fetch slot; raise 404 if missing.
     - Load `slot.task` via ORM relationship (already loaded if using joined load, or access
       attribute to trigger lazy load).
     - `slot.task.status = TaskStatus.pending`
     - `db.delete(slot)`
     - `db.commit()` — both changes are atomic.
     - Return 204.

**Relevant Context:**
- `app/schemas/scheduled_slot.py` — `ScheduledSlotRead`
- `app/models/scheduled_slot.py` — `ScheduledSlot`; `task` relationship
- `app/models/task.py` — `Task`; `TaskStatus`
- The FK `ondelete=CASCADE` on `scheduled_slots.task_id` is for Task deletion, NOT for Slot
  deletion — the task-status reset must be done explicitly in this handler.
- No service module for slots — the logic is self-contained in the router.

---

### ST-4.6 — Register routers in `main.py`
**Status:** [x] done

**Intent:**
Wire all three routers into the FastAPI application under the `/api/v1` prefix.

**Expected Outcomes:**
- `GET /api/v1/blocks`, `GET /api/v1/tasks`, `GET /api/v1/slots` return 200 (not 404).
- `/health` continues to work unchanged.

**Todo List:**
1. Edit `backend/app/main.py`:
   - Import the three routers.
   - Call `app.include_router(blocks_router, prefix="/api/v1")`
     (and analogously for tasks and slots).

**Relevant Context:**
- `backend/app/main.py` — current file has only `/health`; lifespan must not change.
- The prefix `/api/v1` is applied at registration, not inside the router file itself,
  so each router file only declares its own resource prefix (e.g. `/blocks`).

---

### ST-4.7 — `tests/conftest.py`
**Status:** [x] done

**Intent:**
Provide a shared test configuration that gives every router test module:
- An in-memory SQLite database that is isolated per test session.
- The `get_db` dependency overridden so `TestClient` never touches the real MySQL instance.
- SQLite foreign-key enforcement enabled so `ON DELETE CASCADE` is actually exercised.
- `StaticPool` so the TestClient thread and the fixture share the same in-memory database.

**Expected Outcomes:**
- `client` fixture is importable in all test modules.
- `db_session` fixture is importable for direct DB setup (slot creation, etc.).
- `pytest` can run without a running Docker/MySQL container.

**Todo List:**
1. Create `backend/tests/conftest.py`:
   - Use `create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
     poolclass=StaticPool)`.
   - After engine creation, emit `PRAGMA foreign_keys = ON` via an `event.listen` on
     `connect` so SQLite enforces FK constraints.
   - Call `Base.metadata.create_all(bind=test_engine)` once per session.
   - `db_session` fixture: yields a `SessionLocal`-equivalent session bound to the test engine;
     rolls back after each test to isolate state.
   - `client` fixture: creates a `TestClient` with `app.dependency_overrides[get_db]` set to
     a function that yields the test session; override is cleared after the test.
   - The FastAPI `lifespan` must NOT run `Base.metadata.create_all` against the real MySQL
     engine during tests. Achieve this by overriding `get_db` before `TestClient` is instantiated
     (which triggers lifespan); or suppress the lifespan with `with TestClient(app, raise_server_exceptions=True)`.
     Preferred: override `get_db` first, and use `StaticPool` so `create_all` in lifespan
     runs against the in-memory engine via the same pool.

**Relevant Context:**
- `app/database.py` — `get_db`, `Base`, `engine` (real MySQL engine)
- `sqlalchemy.pool.StaticPool` — ensures all connections in the same process use the same
  in-memory SQLite file.
- `sqlalchemy import event` — used to emit `PRAGMA foreign_keys = ON` on every new connection.
- SQLAlchemy renders MySQL ENUMs as `VARCHAR` on SQLite automatically — no schema changes needed.
- `server_default=func.now()` on `created_at` columns: SQLite does not execute server defaults
  during `TestClient` inserts; tests must either provide explicit `created_at` values or
  accept that the column may be `None` in test fixtures. Use `default=func.now()` (client-side)
  in conftest inserts or set the value explicitly.

---

### ST-4.8 — Router tests
**Status:** [x] done

**Intent:**
Write pytest tests for all three routers. Slot creation in tests is performed directly via
`db_session` because `/engine/book` is not yet implemented.

**Expected Outcomes:**
- All tests pass with zero failures using `pytest backend/tests/`.
- No test connects to MySQL.
- Coverage:

#### `test_blocks.py` (≥ 11 tests)

| Test | Assertion |
|---|---|
| POST valid weekly block | 201, `spans_next_day=False` |
| POST valid once block | 201, `date` echoed |
| POST overnight block (22:00–06:00) | 201, `spans_next_day=True` |
| POST block same start/end time | 422 |
| POST weekly block without weekday | 422 |
| POST once block without date | 422 |
| GET /blocks | 200, list contains created block |
| GET /blocks/{id} found | 200, correct fields |
| GET /blocks/{id} not found | 404 |
| PATCH change title only | 200, `spans_next_day` recomputed correctly |
| PATCH that makes start == end | 422 |
| PATCH weekly block, add a date (violates mutual exclusivity) | 422 |
| DELETE block | 204 |
| DELETE non-existent block | 404 |

#### `test_tasks.py` (≥ 8 tests)

| Test | Assertion |
|---|---|
| POST valid task | 201, `status="pending"` |
| POST task with `duration_minutes=0` | 422 |
| POST task with past deadline | 422 |
| GET /tasks | 200, returns list |
| GET /tasks?status=pending | 200, filtered |
| PATCH change title and duration | 200, values updated |
| PATCH send past deadline | 422 |
| PATCH without deadline field | 200 even if stored deadline is in the past |
| DELETE task | 204 |
| DELETE non-existent task | 404 |

#### `test_slots.py` (≥ 4 tests)

| Test | Assertion |
|---|---|
| GET /slots empty | 200, empty list |
| GET /slots/{id} found | 200, correct fields |
| DELETE slot resets task to pending | 204, then GET task confirms status == `pending` |
| DELETE non-existent slot | 404 |

**Todo List:**
1. Create `backend/tests/test_blocks.py` with the test cases listed above.
2. Create `backend/tests/test_tasks.py` with the test cases listed above.
3. Create `backend/tests/test_slots.py` with the test cases listed above.
   - In slot tests, create `Task` and `ScheduledSlot` objects directly via `db_session`
     to simulate what `/engine/book` will do in ST-5.

**Relevant Context:**
- `backend/tests/conftest.py` (ST-4.7) — `client` and `db_session` fixtures
- `backend/tests/test_schemas.py` — existing passing tests; must remain green after ST-4.

---

## Consistency Risk Register

| Risk | Scenario | Mitigation |
|---|---|---|
| Ghost slot | Task deleted while slot exists | FK `ondelete=CASCADE` removes slot automatically |
| Stale status | Slot deleted but task remains `scheduled` | Atomic commit in DELETE /slots/{id} resets task.status |
| Double slot | Second slot attempted for same task | DB UNIQUE on `task_id`; raises IntegrityError (guarded in ST-5) |
| Status drift via PATCH | PATCH task accidentally sets `status` | `TaskUpdate` excludes `status` — impossible via schema |
| Concurrent race | Parallel delete + book on same task | MySQL row-level locks; acceptable for Week 1 single-user MVP |

---

## Files Created or Modified

```
backend/app/services/__init__.py        (new, empty)
backend/app/services/fixed_block.py    (new)
backend/app/services/task.py           (new)
backend/app/routers/__init__.py         (new, empty)
backend/app/routers/blocks.py           (new)
backend/app/routers/tasks.py            (new)
backend/app/routers/slots.py            (new)
backend/app/main.py                     (modified — router registration only)
backend/tests/conftest.py               (new)
backend/tests/test_blocks.py            (new)
backend/tests/test_tasks.py             (new)
backend/tests/test_slots.py             (new)
```

No models, schemas, or database files are modified.
