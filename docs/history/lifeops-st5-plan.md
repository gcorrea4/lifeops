# ST-5 — Deterministic Availability Engine Plan

## Top-Level Overview

**Goal:** Implement the deterministic scheduling engine that suggests available time slots for a
pending Task and allows the user to confirm a booking atomically.

**Scope:**
- `GET /api/v1/engine/suggest` — returns ordered candidate slots.
- `POST /api/v1/engine/book` — validates and books a slot in a single transaction.
- Pure Python engine service with no database calls inside it.
- Full unit test coverage for engine logic; integration tests for both endpoints.
- No AI, no new dependencies beyond what already exists.

**Approach:**
- The engine logic lives in `app/services/engine.py` as pure functions that accept
  plain Python data (intervals, task duration, working-window bounds) and return results.
- DB queries happen exclusively in `app/routers/engine.py`; results are passed to the service.
- `app/core/settings.py` gains two new settings: `WORK_START` and `WORK_END`.
- Existing models, schemas, and other services are not modified.

**Confirmed design decisions:**

| Decision | Value |
|---|---|
| Deadline semantics | Task `end_datetime` must fall within the deadline day's working window |
| Working window | Global default `08:00`–`22:00`; stored in `settings.WORK_START` / `WORK_END` |
| Max suggestions returned | 10 |
| Suggestion order | `start_datetime` ascending |
| Default lookahead | 7 days from `from_date` |
| `from_date` parameter | Optional query param; defaults to today |
| Overnight block handling | Occupied on day D = `[block.start_time, midnight)` of day D and `[midnight, block.end_time]` on day D+1 |
| Adjacent intervals | Merged into the same span (`next.start <= current.end`) |
| Overlapping intervals | Merged into one span |
| `from_date` past value | Returns 422 — cannot suggest slots in the past |

---

## Architecture

```
GET /api/v1/engine/suggest
  │
  ├── router (engine.py)
  │     ├── load Task (404 if missing, 409 if not pending)
  │     ├── load relevant FixedBlocks (weekly + once, covering lookahead window + D-1 overnight)
  │     ├── load ScheduledSlots overlapping the lookahead window
  │     └── call engine service → return list[SlotSuggestion]
  │
  └── service (services/engine.py)  — pure functions, no DB
        ├── build_occupied_intervals(blocks, slots, day, work_start, work_end)
        ├── merge_intervals(intervals)
        ├── compute_free_intervals(occupied, work_start, work_end)
        ├── filter_by_duration(free_intervals, duration_minutes)
        └── suggest_slots(task, blocks, slots, from_date, lookahead, work_start, work_end) -> list[SlotSuggestion]

POST /api/v1/engine/book
  │
  └── router (engine.py)
        ├── load Task (404, 409 if not pending)
        ├── calculate end_datetime = start_datetime + duration_minutes
        ├── validate deadline (end_datetime must be within deadline day working window)
        ├── check FixedBlock collision (revalidate, do not trust prior suggestion)
        ├── check ScheduledSlot collision (revalidate)
        ├── create ScheduledSlot
        ├── Task.status = scheduled
        └── single db.commit()
```

---

## Interval Representation

Intervals are represented as plain Python tuples of `datetime` objects:

```
Interval = tuple[datetime, datetime]   # (start_inclusive, end_exclusive)
```

All interval arithmetic is done in terms of `datetime` objects anchored to a specific date,
making overnight splits straightforward and comparison unambiguous.

---

## Sub-Tasks

---

### ST-5.1 — `app/core/settings.py` — Add working window settings
**Status:** [x] done

**Intent:**
Add `WORK_START` and `WORK_END` to the global `Settings` class so the engine can be
configured without touching source code.

**Expected Outcomes:**
- `settings.WORK_START` returns a `datetime.time` object (default `08:00`).
- `settings.WORK_END` returns a `datetime.time` object (default `22:00`).
- Existing settings are unchanged.

**Todo List:**
1. Open `backend/app/core/settings.py`.
2. Import `time` from `datetime`.
3. Add `WORK_START: time = time(8, 0)` to the `Settings` class.
4. Add `WORK_END: time = time(22, 0)` to the `Settings` class.

**Relevant Context:**
- `backend/app/core/settings.py` — existing `Settings(BaseSettings)` class.
- These fields use `time` literals as defaults. Pydantic BaseSettings can coerce
  a `"HH:MM"` string from a `.env` file into a `time` object automatically.

---

### ST-5.2 — `app/services/engine.py` — Pure engine functions
**Status:** [x] done

**Intent:**
Implement the deterministic availability engine as a collection of pure functions.
No database calls. All inputs arrive as pre-loaded Python objects.

**Expected Outcomes:**
- All five core functions exist and are individually importable.
- `suggest_slots(...)` returns a list of `SlotSuggestion` objects, at most 10, ordered
  by `start_datetime` ascending.
- Functions handle all edge cases: empty schedule, full-day occupancy, overnight blocks,
  adjacent intervals, deadline boundaries.

**Interval representation:**
```
Interval = tuple[datetime, datetime]
```
Both endpoints are concrete `datetime` objects anchored to the same calendar date (or the
next calendar date for overnight overflow). `end` is exclusive.

**Core functions to implement:**

#### `blocks_for_day(blocks, day) -> list[FixedBlock]`
Returns FixedBlocks that _originate_ on `day`:
- weekly blocks where `block.weekday == day.weekday()`.
- once blocks where `block.date == day`.

#### `overnight_blocks_from_previous_day(blocks, day) -> list[FixedBlock]`
Returns FixedBlocks that originated on `day - 1` AND `spans_next_day = True`.
These contribute a `[midnight, block.end_time]` interval on `day`.

#### `block_to_intervals(block, day) -> list[Interval]`
Converts one FixedBlock to one or two `datetime` intervals anchored to `day`.
- Non-overnight: returns `[(day+start_time, day+end_time)]`.
- Overnight (spans_next_day=True): returns `[(day+start_time, day+midnight)]`.
  The second half (`midnight → end_time` on the next day) is handled by
  `overnight_blocks_from_previous_day` when processing day+1.
- When called from `overnight_blocks_from_previous_day`: returns `[(day+midnight, day+end_time)]`.

#### `slots_to_intervals(slots, day) -> list[Interval]`
Converts ScheduledSlots that overlap `day` into `Interval` objects, clipped to `day`
if they straddle midnight (rare, but correct).

#### `merge_intervals(intervals: list[Interval]) -> list[Interval]`
Sorts intervals by start, then merges both overlapping AND adjacent spans.
Two intervals are merged when `next.start <= current.end` (i.e., the next interval
starts at or before the current interval ends — they touch or overlap).

Example: `09:00–10:00` and `10:00–11:00` → `09:00–11:00`.

**Algorithm:**
```
sort by start
for each interval:
    if list is empty or current.start > last.end:
        append
    else:
        last.end = max(last.end, current.end)
```

#### `compute_free_intervals(occupied: list[Interval], work_start: time, work_end: time, day: date) -> list[Interval]`
Given a sorted, merged list of occupied intervals and the working window bounds,
returns the gaps within `[day+work_start, day+work_end)`.
Works by walking through the occupied list and collecting gaps.

#### `filter_by_duration(free: list[Interval], duration_minutes: int) -> list[Interval]`
Keeps only free intervals where `(end - start).total_seconds() / 60 >= duration_minutes`.

#### `suggest_slots(task, blocks, slots, from_date, lookahead_days, work_start, work_end) -> list[SlotSuggestion]`
Top-level function. For each day in `[from_date, from_date + lookahead_days)`:
1. Collect `blocks_for_day(blocks, day)` + `overnight_blocks_from_previous_day(blocks, day)`.
2. Convert to intervals.
3. Convert overlapping slots to intervals.
4. Merge all occupied intervals.
5. Compute free intervals within working window.
6. Filter by task.duration_minutes.
7. For each free interval that fits, emit `SlotSuggestion(start_datetime=interval.start, end_datetime=interval.start + duration, date=day)`.
   Do NOT emit a suggestion if `end_datetime` falls outside the working window or past the deadline constraint.
8. Stop after collecting 10 total suggestions.

**Deadline enforcement inside `suggest_slots`:**
- If `task.deadline` is set, do not emit any suggestion where `end_datetime` is after
  `datetime.combine(task.deadline, work_end)`.
- Also do not iterate days past `task.deadline`.

**Todo List:**
1. Create `backend/app/services/engine.py`.
2. Implement `blocks_for_day`.
3. Implement `overnight_blocks_from_previous_day`.
4. Implement `block_to_intervals` (non-overnight case).
5. Implement `block_to_intervals` (overnight origin case).
6. Implement `overnight_interval` helper (called when processing D+1 for a D-origin overnight block).
7. Implement `slots_to_intervals`.
8. Implement `merge_intervals`.
9. Implement `compute_free_intervals`.
10. Implement `filter_by_duration`.
11. Implement `suggest_slots`.

**Relevant Context:**
- `backend/app/models/fixed_block.py` — `FixedBlock.spans_next_day`, `FixedBlock.weekday`, `FixedBlock.date`, `FixedBlock.start_time`, `FixedBlock.end_time`.
- `backend/app/models/scheduled_slot.py` — `ScheduledSlot.start_datetime`, `ScheduledSlot.end_datetime`.
- `backend/app/schemas/engine.py` — `SlotSuggestion` has `start_datetime`, `end_datetime`, `date`.
- No imports from `app.database` or `app.routers` — this file is pure logic only.

---

### ST-5.3 — `app/routers/engine.py` — Engine router
**Status:** [x] done

**Intent:**
Implement the two HTTP endpoints that wire the database layer to the engine service.
All DB access lives here; the service receives only loaded data.

**Expected Outcomes:**
- `GET  /api/v1/engine/suggest?task_id=N&from_date=YYYY-MM-DD` returns `list[SlotSuggestion]`.
- `POST /api/v1/engine/book` creates a `ScheduledSlot` and transitions Task to `scheduled`
  in a single commit.
- All HTTP error codes described in the Error Reference section are respected.
- The router imports `suggest_slots` from `app.services.engine` and the two new settings.

**`GET /engine/suggest` query parameters:**
- `task_id: int` — required.
- `from_date: date = Query(default=None)` — optional; defaults to `date.today()` if omitted.
  A past date (strictly before today) returns `422` with detail `"from_date cannot be in the past"`.

**`GET /engine/suggest` flow:**
1. Load `Task` by `task_id` and `user_id=1`. Return `404` if not found.
2. If `task.status != pending`, return `409` with detail `"task is not pending"`.
3. Resolve `from_date` (default: `date.today()`). If the resolved value is before today, return `422`.
4. Load all `FixedBlock` rows for `user_id=1`.
   (Full table load is acceptable for Week 1; no complex date filtering needed here.)
5. Load all `ScheduledSlot` rows for `user_id=1` whose `start_datetime` falls within
   `[from_date, from_date + lookahead_days + 1 day)` (the +1 covers overnight overflow).
6. Call `suggest_slots(task, blocks, slots, from_date, lookahead_days=7, work_start=settings.WORK_START, work_end=settings.WORK_END)`.
7. Return the list.

**`POST /engine/book` body:** `BookRequest { task_id: int, start_datetime: datetime }`

**`POST /engine/book` flow:**
1. Load `Task` by `task_id` and `user_id=1`. Return `404` if not found.
2. If `task.status != pending`, return `409` with detail `"task is not pending"`.
   (Also covers already-scheduled tasks.)
3. Compute `end_datetime = start_datetime + timedelta(minutes=task.duration_minutes)`.
4. If `task.deadline` is set, verify `end_datetime <= datetime.combine(task.deadline, settings.WORK_END)`.
   Return `422` on violation with detail `"slot would exceed task deadline"`.
5. Load all `FixedBlock` rows for `user_id=1`.
6. For each FixedBlock relevant to the booking day (including overnight from D-1),
   check whether `[start_datetime, end_datetime)` overlaps `[block_start, block_end)`.
   Return `409` on collision with detail `"slot conflicts with a fixed block"`.
7. Load all `ScheduledSlot` rows for `user_id=1` that overlap
   `[start_datetime, end_datetime)`.
   Return `409` on collision with detail `"slot conflicts with an existing scheduled slot"`.
8. Create `ScheduledSlot(task_id=task.id, user_id=1, start_datetime=..., end_datetime=...)`.
9. Set `task.status = TaskStatus.scheduled`.
10. `db.add(slot)`, `db.commit()`, `db.refresh(slot)`.
11. Return `ScheduledSlotRead` with HTTP 201.

**Interval overlap test (used in steps 6 and 7):**
```
intervals_overlap(a_start, a_end, b_start, b_end) -> bool:
    return a_start < b_end and b_start < a_end
```

**Todo List:**
1. Create `backend/app/routers/engine.py`.
2. Implement `GET /engine/suggest`.
3. Implement `POST /engine/book`.
4. Register the engine router in `backend/app/main.py` under prefix `/api/v1`.

**Relevant Context:**
- `backend/app/routers/blocks.py` — reference for router pattern (prefix, tags, get_db dependency).
- `backend/app/models/task.py` — `Task`, `TaskStatus`.
- `backend/app/models/fixed_block.py` — `FixedBlock`.
- `backend/app/models/scheduled_slot.py` — `ScheduledSlot`.
- `backend/app/schemas/engine.py` — `SlotSuggestion`, `BookRequest`.
- `backend/app/schemas/scheduled_slot.py` — `ScheduledSlotRead`.
- `backend/app/services/engine.py` (ST-5.2) — `suggest_slots`.
- `backend/app/core/settings.py` — `settings.WORK_START`, `settings.WORK_END`.
- `BookRequest` already validates that `start_datetime` is in the future (Pydantic validator).

---

### ST-5.4 — Unit tests for `services/engine.py`
**Status:** [x] done

**Intent:**
Verify the pure engine functions in isolation, without a database, using hand-crafted
interval data. These tests are the primary safety net for the algorithm.

**Expected Outcomes:**
- All unit tests pass with `pytest backend/tests/test_engine_service.py`.
- No database connection required.
- Covers all specified edge cases.

**Test cases (file: `backend/tests/test_engine_service.py`):**

| Test | What it verifies |
|---|---|
| `test_merge_no_overlap` | Two non-overlapping intervals remain separate |
| `test_merge_overlapping` | Two overlapping intervals merge into one |
| `test_merge_adjacent` | Adjacent intervals (end==start) ARE merged into one |
| `test_merge_contained` | One interval fully contained within another collapses to outer |
| `test_merge_empty` | Empty list returns empty list |
| `test_free_intervals_empty_occupied` | Full working window is free when nothing is occupied |
| `test_free_intervals_full_day_blocked` | Zero free intervals when whole window is occupied |
| `test_free_intervals_partial_overlap_start` | Correctly trims gap at start |
| `test_free_intervals_partial_overlap_end` | Correctly trims gap at end |
| `test_free_intervals_multiple_gaps` | Multiple gaps returned in order |
| `test_filter_by_duration_exact_fit` | Interval exactly fitting duration is kept |
| `test_filter_by_duration_too_short` | Interval shorter than duration is dropped |
| `test_suggest_empty_schedule` | Returns slots across multiple days when no blocks exist |
| `test_suggest_full_day_blocked` | No slots on fully blocked day, slots on next day |
| `test_suggest_overnight_block_origin_day` | Overnight block occupies end of day D |
| `test_suggest_overnight_block_next_day` | Overnight block occupies start of day D+1 |
| `test_suggest_overlapping_blocks` | Two overlapping blocks merge and leave correct gap |
| `test_suggest_deadline_filters_slots_after_deadline` | Slots after deadline not returned |
| `test_suggest_deadline_boundary_slot_fits` | Slot ending exactly at work_end on deadline day is returned |
| `test_suggest_deadline_boundary_slot_too_long` | Slot that would exceed work_end on deadline day is rejected |
| `test_suggest_task_fits_exactly` | Task duration exactly fills remaining free interval |
| `test_suggest_max_10_suggestions` | Never returns more than 10 suggestions |
| `test_suggest_existing_slot_blocks_time` | Existing ScheduledSlot occupies its interval |
| `test_blocks_for_day_weekly_match` | Correct weekly block returned for matching weekday |
| `test_blocks_for_day_weekly_no_match` | No weekly block returned for non-matching weekday |
| `test_blocks_for_day_once_match` | Correct once block returned for matching date |
| `test_overnight_from_previous_day` | Block from D-1 with spans_next_day=True is returned |

**Todo List:**
1. Create `backend/tests/test_engine_service.py`.
2. Implement all test cases listed above using plain Python objects (no DB, no TestClient).
3. Use `datetime` and `date` literals directly — no fixtures needed.

**Relevant Context:**
- `backend/app/services/engine.py` (ST-5.2) — functions under test.
- `backend/app/models/fixed_block.py` — `FixedBlock` model (instantiate directly for tests).
- `backend/app/models/scheduled_slot.py` — `ScheduledSlot` model (instantiate directly for tests).
- `backend/app/schemas/engine.py` — `SlotSuggestion`.

---

### ST-5.5 — Integration tests for `routers/engine.py`
**Status:** [x] done

**Intent:**
Verify the engine endpoints end-to-end through the TestClient using the in-memory SQLite
database. These tests exercise the router logic (DB queries, HTTP contract, error codes).

**Expected Outcomes:**
- All integration tests pass with `pytest backend/tests/test_engine_router.py`.
- No MySQL connection required.
- Existing 58 tests continue to pass.

**Test cases (file: `backend/tests/test_engine_router.py`):**

#### `GET /api/v1/engine/suggest`

| Test | Expected HTTP | Scenario |
|---|---|---|
| `test_suggest_task_not_found` | 404 | task_id does not exist |
| `test_suggest_task_not_pending` | 409 | task is already scheduled |
| `test_suggest_no_blocks_returns_slots` | 200, non-empty list | empty schedule, 7-day window |
| `test_suggest_full_day_blocked_no_results` | 200, empty list | every hour within working window is a FixedBlock |
| `test_suggest_with_from_date` | 200 | from_date param respected; no slots before that date |
| `test_suggest_from_date_in_past` | 422 | from_date is yesterday → rejected |
| `test_suggest_respects_deadline` | 200 | slots after deadline not returned |
| `test_suggest_overnight_block_respected` | 200 | overnight block reduces available window on next day |
| `test_suggest_existing_slot_excluded` | 200 | existing ScheduledSlot occupies its window |

#### `POST /api/v1/engine/book`

| Test | Expected HTTP | Scenario |
|---|---|---|
| `test_book_task_not_found` | 404 | task_id does not exist |
| `test_book_task_not_pending` | 409 | task already scheduled |
| `test_book_exceeds_deadline` | 422 | end_datetime beyond work_end on deadline day |
| `test_book_conflicts_with_fixed_block` | 409 | start_datetime overlaps a FixedBlock |
| `test_book_conflicts_with_existing_slot` | 409 | start_datetime overlaps an existing ScheduledSlot |
| `test_book_success` | 201, ScheduledSlotRead | valid booking; task.status == scheduled |
| `test_book_duplicate_booking_rejected` | 409 | same task booked twice (UNIQUE guard) |
| `test_book_past_datetime_rejected` | 422 | BookRequest Pydantic validator rejects past start |

**Todo List:**
1. Create `backend/tests/test_engine_router.py`.
2. Use the existing `client` and `db_session` fixtures from `conftest.py`.
3. For tests requiring a `scheduled` task, create a `ScheduledSlot` directly via `db_session`
   (same pattern as `test_slots.py`).
4. Implement all test cases listed above.

**Relevant Context:**
- `backend/tests/conftest.py` — `client`, `db_session` fixtures.
- `backend/tests/test_slots.py` — reference for `_make_task` / `_make_slot` helper pattern.
- `backend/app/routers/engine.py` (ST-5.3) — router under test.

---

## Error Reference

| Endpoint | Condition | HTTP | Detail |
|---|---|---|---|
| `GET /suggest` | task not found | 404 | `"task not found"` |
| `GET /suggest` | task not pending | 409 | `"task is not pending"` |
| `GET /suggest` | from_date in the past | 422 | `"from_date cannot be in the past"` |
| `POST /book` | task not found | 404 | `"task not found"` |
| `POST /book` | task not pending | 409 | `"task is not pending"` |
| `POST /book` | end_datetime exceeds deadline | 422 | `"slot would exceed task deadline"` |
| `POST /book` | overlaps FixedBlock | 409 | `"slot conflicts with a fixed block"` |
| `POST /book` | overlaps ScheduledSlot | 409 | `"slot conflicts with an existing scheduled slot"` |
| `POST /book` | start_datetime in the past | 422 | (raised by `BookRequest` Pydantic validator) |

---

## Files to Create or Modify

```
backend/app/core/settings.py            (modified — add WORK_START, WORK_END)
backend/app/services/engine.py          (new — pure engine logic)
backend/app/routers/engine.py           (new — HTTP endpoints)
backend/app/main.py                     (modified — register engine router)
backend/tests/test_engine_service.py   (new — pure unit tests)
backend/tests/test_engine_router.py    (new — integration tests)
```

No models, existing schemas, or other routers are modified.

---

## Consistency Risk Register

| Risk | Scenario | Mitigation |
|---|---|---|
| Stale suggestion | User confirms a suggestion that became invalid between suggest and book | `POST /book` fully revalidates; never trusts prior suggestion |
| Double booking (race) | Two concurrent book requests for same task | DB UNIQUE constraint on `scheduled_slots.task_id` is final guard; acceptable for Week 1 single-user MVP |
| Overnight boundary error | Overnight block from D-1 not considered for day D | `overnight_blocks_from_previous_day` function explicitly handles this; covered by unit tests |
| Deadline off-by-one | Slot starts before deadline but ends after `work_end` | Deadline enforcement compares `end_datetime <= datetime.combine(deadline, work_end)`; covered by boundary unit tests |
| Working window not enforced | Engine returns slots outside 08:00–22:00 | `compute_free_intervals` clips all output to `[work_start, work_end)` per day |
| SQLite vs MySQL time type | SQLite stores time as string | Tests use `datetime` objects throughout; no time-only comparisons in test DB |
