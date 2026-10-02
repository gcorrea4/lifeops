# ST-3 — Pydantic Schemas Plan

## Top-Level Overview

**Goal:** Create `app/schemas/` with all Pydantic request/response schemas needed for the
three domain entities and the availability engine. No routers, no engine logic.

**Scope:** New files only. No existing file is modified.

**Approach:**
- Mirror each SQLAlchemy model as three schema variants (Create / Update / Read).
- Pydantic validates only what can be checked from the fields present in the incoming payload alone.
- Cross-field rules that require the full merged state (existing DB record + patch fields) are the
  responsibility of the router/service layer, not Pydantic.
- Leave DB-level integrity rules (FKs, UNIQUE, end > start on ScheduledSlot) to the database.
- All Read schemas use `model_config = ConfigDict(from_attributes=True)` for ORM → Pydantic mapping.
- Reuse enums from `app/models/enums.py` directly — no duplication.

**Layer responsibility boundary:**

| Concern | Owner |
|---|---|
| Individual field format/range (weekday 0–6, duration > 0) | Pydantic |
| `start_time != end_time` on Create (both fields always present) | Pydantic |
| `deadline` not in the past on Create | Pydantic |
| `spans_next_day` computation (`end_time < start_time`) | Router/service (after merge) |
| Recurrence mutual exclusivity (`weekly` ↔ weekday, `once` ↔ date) | Router/service (after merge) |
| `end_datetime` computation (`start + duration`) | Router/service |
| Task status transitions | Engine actions only |

**Out of scope:**
- CRUD routers (ST-4)
- Availability engine (ST-5)
- Any change to models, database.py, main.py

---

## Sub-Tasks

---

### ST-3.1 — `schemas/fixed_block.py`
**Status:** [x] done

**Intent:**
Define the three FixedBlock schema variants with all business-rule validators.

**Expected Outcomes:**
- `FixedBlockCreate`, `FixedBlockUpdate`, `FixedBlockRead` exist and are importable.
- `weekday` outside 0–6 raises a validation error on both Create and Update.
- `start_time == end_time` raises a validation error on Create (both fields are always present).
- `spans_next_day` is NOT a field on Create or Update inputs — it is never sent by the client.
- No cross-field recurrence validator exists in Pydantic — that check runs in the router/service.

**Todo List:**
1. Create `backend/app/schemas/__init__.py` (empty, marks package).
2. Create `backend/app/schemas/fixed_block.py` with:
   - `FixedBlockBase` — shared optional fields: `title`, `recurrence_type`, `weekday`, `date`,
     `start_time`, `end_time`; all `Optional` for reuse in Update.
     Validator on `weekday`: if provided, must be in 0–6.
   - `FixedBlockCreate(FixedBlockBase)` — makes `title`, `recurrence_type`, `start_time`,
     `end_time` required. `spans_next_day` is absent (not a client field).
     Single cross-field validator: `start_time != end_time` (safe because both fields are
     always present on Create).
     No recurrence mutual-exclusivity check here — router handles it after DB merge.
   - `FixedBlockUpdate(FixedBlockBase)` — all fields `Optional`. No cross-field validators.
     The `weekday` range validator from `FixedBlockBase` still applies when the field is present.
   - `FixedBlockRead` — all model fields including `id`, `user_id`, `spans_next_day`,
     `created_at`; `model_config = ConfigDict(from_attributes=True)`.
     Does NOT inherit from `FixedBlockCreate` (avoids carrying Create constraints into Read).

**Relevant Context:**
- Model: `backend/app/models/fixed_block.py`
- Enums: `backend/app/models/enums.py` — `RecurrenceType`
- DB CHECK enforces weekday range and mutual exclusivity as the last line of defence.
- Recurrence mutual-exclusivity and `spans_next_day` computation belong to the router/service
  (ST-4), where the full merged record state is available.

---

### ST-3.2 — `schemas/task.py`
**Status:** [x] done

**Intent:**
Define Task schema variants. Status is excluded from Create and Update — managed only through
engine actions.

**Expected Outcomes:**
- `TaskCreate`, `TaskUpdate`, `TaskRead` exist and are importable.
- `duration_minutes <= 0` raises a validation error.
- `deadline` in the past raises a validation error on create.
- `status` is not a field on `TaskCreate` or `TaskUpdate`.

**Todo List:**
1. Create `backend/app/schemas/task.py` with:
   - `TaskBase` — shared optional fields: `title`, `duration_minutes`, `deadline`, `priority`.
   - `TaskCreate(TaskBase)` — makes `title`, `duration_minutes` required; `priority` defaults to
     `Priority.medium`; `deadline` optional.
     Validators:
     - `duration_minutes > 0`.
     - `deadline >= today` when provided.
   - `TaskUpdate(TaskBase)` — all fields `Optional`; same `duration_minutes` validator applied
     only when the field is present.
   - `TaskRead(TaskBase)` — adds `id`, `user_id`, `status`, `created_at`;
     `model_config = ConfigDict(from_attributes=True)`.

**Relevant Context:**
- Model: `backend/app/models/task.py`
- Enums: `backend/app/models/enums.py` — `Priority`, `TaskStatus`
- `status` defaults to `pending` at the DB level; Pydantic never sets it.
- Decision (confirmed): `TaskUpdate` does NOT include `status`.

---

### ST-3.3 — `schemas/scheduled_slot.py`
**Status:** [x] done

**Intent:**
Define the ScheduledSlot read schema. No Create schema needed here — slot creation goes through
`BookRequest` in `engine.py`.

**Expected Outcomes:**
- `ScheduledSlotRead` exists and is importable.
- Maps cleanly from the ORM model.

**Todo List:**
1. Create `backend/app/schemas/scheduled_slot.py` with:
   - `ScheduledSlotRead` — fields: `id`, `task_id`, `user_id`, `start_datetime`,
     `end_datetime`, `created_at`; `model_config = ConfigDict(from_attributes=True)`.

**Relevant Context:**
- Model: `backend/app/models/scheduled_slot.py`
- `end_datetime` is always computed server-side (start + duration); never accepted from client.

---

### ST-3.4 — `schemas/engine.py`
**Status:** [x] done

**Intent:**
Define the two schemas used by the availability engine endpoints.

**Expected Outcomes:**
- `SlotSuggestion` and `BookRequest` exist and are importable.
- `BookRequest.start_datetime` in the past raises a validation error.

**Todo List:**
1. Create `backend/app/schemas/engine.py` with:
   - `SlotSuggestion` — fields: `start_datetime` (`datetime`), `end_datetime` (`datetime`),
     `date` (`date`); read-only, no validators needed.
   - `BookRequest` — fields: `task_id` (`int`), `start_datetime` (`datetime`).
     Validator: `start_datetime` must be in the future (>= now UTC).

**Relevant Context:**
- Used by ST-5 engine router: `GET /engine/suggest` returns `list[SlotSuggestion]`;
  `POST /engine/book` accepts `BookRequest`.

---

### ST-3.5 — Smoke tests for schemas
**Status:** [x] done

**Intent:**
Write lightweight pytest unit tests that exercise the Pydantic validators directly — no
database, no HTTP layer required. Tests cover only what Pydantic itself validates; cross-field
recurrence rules and `spans_next_day` computation are tested in ST-4 (router/service layer).

**Expected Outcomes:**
- Tests in `backend/tests/test_schemas.py`.
- At least one valid and one invalid case per Pydantic validator.
- `pytest` passes with zero failures.

**Todo List:**
1. Create `backend/tests/test_schemas.py`.
2. FixedBlock tests:
   - Valid `FixedBlockCreate` (weekly, weekday=0, date=None) → no error.
   - Valid `FixedBlockCreate` (once, date set, weekday=None) → no error.
   - `weekday = 7` on Create → `ValidationError` (out of range).
   - `weekday = -1` on Create → `ValidationError` (out of range).
   - `start_time == end_time` on Create → `ValidationError`.
   - `weekday = 7` on Update → `ValidationError` (range validator still applies).
   - NOTE: recurrence mutual-exclusivity tests (weekly+no weekday, once+no date) and
     `spans_next_day` tests belong in the ST-4 router/service tests, not here.
3. Task tests:
   - `duration_minutes = 0` → `ValidationError`.
   - `duration_minutes = -5` → `ValidationError`.
   - `deadline` in the past → `ValidationError`.
   - `deadline` today → no error.
   - `deadline` in the future → no error.
4. BookRequest test:
   - `start_datetime` in the past → `ValidationError`.
   - `start_datetime` in the future → no error.

**Relevant Context:**
- Tests are pure Python; import schemas directly.
- `backend/tests/` directory already exists (created in ST-1/ST-2 scaffold).

---

## Validation Boundary Summary

| Rule | Pydantic | Router/Service | DB |
|---|---|---|---|
| `weekday` in 0–6 | ✅ field validator | — | ✅ CHECK |
| `start_time != end_time` on Create | ✅ cross-field (both always present) | — | — |
| `weekly` requires `weekday`, forbids `date` | — | ✅ after merge | ✅ CHECK |
| `once` requires `date`, forbids `weekday` | — | ✅ after merge | ✅ CHECK |
| `spans_next_day = end_time < start_time` | — | ✅ after merge | stored value |
| `duration_minutes > 0` | ✅ field validator | — | ✅ CHECK |
| `deadline` not in the past on Create | ✅ field validator | — | — |
| `end_datetime = start + duration` | — | ✅ computed | — |
| `end_datetime > start_datetime` on slot | — | — | ✅ CHECK |
| `start_datetime` in the future (BookRequest) | ✅ field validator | — | — |
| One slot per task | — | — | ✅ UNIQUE |
| `task_id` FK integrity | — | — | ✅ FK CASCADE |

---

## Files Created

```
backend/app/schemas/__init__.py      (new, empty)
backend/app/schemas/fixed_block.py  (new)
backend/app/schemas/task.py         (new)
backend/app/schemas/scheduled_slot.py (new)
backend/app/schemas/engine.py       (new)
backend/tests/test_schemas.py       (new)
```

No existing files are modified.
