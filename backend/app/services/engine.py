"""Deterministic availability engine — pure functions, no database calls.

All database queries happen in the router layer. Data is passed in as plain
Python objects. Every function here is fully unit-testable without a running
database.

Interval representation
-----------------------
An Interval is a (start, end) tuple of naive datetime objects where:
  - start is inclusive
  - end   is exclusive

Both endpoints are anchored to a concrete calendar date. Overnight blocks are
split into two intervals by the caller before being passed to merge_intervals.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.fixed_block import FixedBlock
    from app.models.scheduled_slot import ScheduledSlot
    from app.schemas.engine import SlotSuggestion

# ---------------------------------------------------------------------------
# Type alias
# ---------------------------------------------------------------------------

Interval = tuple[datetime, datetime]

# ---------------------------------------------------------------------------
# Day-level block helpers
# ---------------------------------------------------------------------------


def blocks_for_day(blocks: list["FixedBlock"], day: date) -> list["FixedBlock"]:
    """Return FixedBlocks that *originate* on ``day``.

    - weekly blocks: block.weekday == day.weekday()
    - once blocks:   block.date == day
    """
    result: list["FixedBlock"] = []
    for block in blocks:
        if block.recurrence_type.value == "weekly":
            if block.weekday == day.weekday():
                result.append(block)
        else:  # once
            if block.date == day:
                result.append(block)
    return result


def overnight_blocks_from_previous_day(
    blocks: list["FixedBlock"], day: date
) -> list["FixedBlock"]:
    """Return FixedBlocks that originated on ``day - 1`` and span into ``day``.

    These blocks contribute a [midnight, block.end_time] interval on ``day``.
    """
    prev = day - timedelta(days=1)
    result: list["FixedBlock"] = []
    for block in blocks:
        if not block.spans_next_day:
            continue
        if block.recurrence_type.value == "weekly":
            if block.weekday == prev.weekday():
                result.append(block)
        else:  # once
            if block.date == prev:
                result.append(block)
    return result


# ---------------------------------------------------------------------------
# Interval conversion helpers
# ---------------------------------------------------------------------------


def _combine(d: date, t: time) -> datetime:
    """Combine a date and a time into a naive datetime."""
    return datetime.combine(d, t)


def block_to_interval(block: "FixedBlock", day: date) -> Interval:
    """Convert a FixedBlock that *originates* on ``day`` to an interval.

    For an overnight block the interval covers only the first half of the block:
    [start_time, midnight).  The second half (midnight → end_time on day+1) is
    produced by ``overnight_tail_interval`` when processing day+1.
    """
    start = _combine(day, block.start_time)
    if block.spans_next_day:
        end = _combine(day + timedelta(days=1), time(0, 0))
    else:
        end = _combine(day, block.end_time)
    return (start, end)


def overnight_tail_interval(block: "FixedBlock", day: date) -> Interval:
    """Return the tail interval [midnight, end_time) on ``day`` for an overnight
    block that originated on ``day - 1``.
    """
    start = _combine(day, time(0, 0))
    end = _combine(day, block.end_time)
    return (start, end)


def slots_to_intervals(slots: list["ScheduledSlot"], day: date) -> list[Interval]:
    """Convert ScheduledSlots that overlap ``day`` into Interval objects.

    Intervals are clipped to day boundaries so they do not extend into adjacent
    days (handles the rare case of a slot that crosses midnight).
    """
    day_start = _combine(day, time(0, 0))
    day_end = _combine(day + timedelta(days=1), time(0, 0))

    result: list[Interval] = []
    for slot in slots:
        s = slot.start_datetime
        e = slot.end_datetime
        # Clip to day boundaries
        clipped_start = max(s, day_start)
        clipped_end = min(e, day_end)
        if clipped_start < clipped_end:
            result.append((clipped_start, clipped_end))
    return result


# ---------------------------------------------------------------------------
# Core interval algorithms
# ---------------------------------------------------------------------------


def merge_intervals(intervals: list[Interval]) -> list[Interval]:
    """Sort and merge overlapping *and* adjacent intervals.

    Two intervals are merged when ``next.start <= current.end``, i.e., they
    touch or overlap.

    Example:
        09:00–10:00 + 10:00–11:00  →  09:00–11:00  (adjacent, merged)
        09:00–10:30 + 10:00–11:00  →  09:00–11:00  (overlapping, merged)
        09:00–10:00 + 10:01–11:00  →  [09:00–10:00, 10:01–11:00]  (gap, kept separate)
    """
    if not intervals:
        return []

    sorted_intervals = sorted(intervals, key=lambda iv: iv[0])
    merged: list[list[datetime]] = [list(sorted_intervals[0])]

    for start, end in sorted_intervals[1:]:
        last = merged[-1]
        if start <= last[1]:
            # Overlapping or adjacent — extend the current span
            last[1] = max(last[1], end)
        else:
            merged.append([start, end])

    return [(s, e) for s, e in merged]


def compute_free_intervals(
    occupied: list[Interval],
    work_start: time,
    work_end: time,
    day: date,
) -> list[Interval]:
    """Return the free gaps within [work_start, work_end) on ``day``.

    ``occupied`` must already be sorted and merged (call ``merge_intervals``
    first).
    """
    window_start = _combine(day, work_start)
    window_end = _combine(day, work_end)

    free: list[Interval] = []
    cursor = window_start

    for occ_start, occ_end in occupied:
        # Skip occupied intervals that are entirely before the window
        if occ_end <= cursor:
            continue
        # Skip occupied intervals that are entirely after the window
        if occ_start >= window_end:
            break
        # Clip occupied interval to the window
        occ_start = max(occ_start, cursor)
        occ_end = min(occ_end, window_end)

        if occ_start > cursor:
            free.append((cursor, occ_start))

        cursor = max(cursor, occ_end)
        if cursor >= window_end:
            break

    # Remaining gap at end of window
    if cursor < window_end:
        free.append((cursor, window_end))

    return free


def filter_by_duration(
    free: list[Interval], duration_minutes: int
) -> list[Interval]:
    """Keep only intervals whose length is >= ``duration_minutes``."""
    min_delta = timedelta(minutes=duration_minutes)
    return [(s, e) for s, e in free if (e - s) >= min_delta]


# ---------------------------------------------------------------------------
# Top-level suggest function
# ---------------------------------------------------------------------------


def suggest_slots(
    task: object,
    blocks: list["FixedBlock"],
    slots: list["ScheduledSlot"],
    from_date: date,
    lookahead_days: int,
    work_start: time,
    work_end: time,
) -> list["SlotSuggestion"]:
    """Return at most 10 candidate SlotSuggestion objects, ordered by start_datetime.

    Parameters
    ----------
    task:
        The Task ORM object. Must have ``duration_minutes`` and optional ``deadline``.
    blocks:
        All FixedBlock rows for the user. The function filters internally per day.
    slots:
        Pre-loaded ScheduledSlot rows that fall within (or near) the lookahead window.
    from_date:
        First day to consider.
    lookahead_days:
        Number of calendar days to inspect starting from ``from_date``.
    work_start / work_end:
        Daily working window boundaries (time objects).
    """
    # Import here to avoid circular imports — engine.py must stay import-free
    # from the app.schemas package at module load time so it can be tested
    # without a full FastAPI app context.
    from app.schemas.engine import SlotSuggestion

    MAX_SUGGESTIONS = 10

    duration = timedelta(minutes=task.duration_minutes)
    deadline: date | None = getattr(task, "deadline", None)

    # Deadline ceiling: the task must finish by work_end on the deadline day
    deadline_ceiling: datetime | None = None
    if deadline is not None:
        deadline_ceiling = datetime.combine(deadline, work_end)

    suggestions: list[SlotSuggestion] = []

    for day_offset in range(lookahead_days):
        if len(suggestions) >= MAX_SUGGESTIONS:
            break

        day = from_date + timedelta(days=day_offset)

        # Do not generate suggestions beyond the deadline day
        if deadline is not None and day > deadline:
            break

        # --- Build occupied intervals for this day ---
        origin_blocks = blocks_for_day(blocks, day)
        tail_blocks = overnight_blocks_from_previous_day(blocks, day)

        occupied: list[Interval] = []
        for block in origin_blocks:
            occupied.append(block_to_interval(block, day))
        for block in tail_blocks:
            occupied.append(overnight_tail_interval(block, day))
        occupied.extend(slots_to_intervals(slots, day))

        # --- Merge, find free gaps, filter by duration ---
        occupied = merge_intervals(occupied)
        free = compute_free_intervals(occupied, work_start, work_end, day)
        free = filter_by_duration(free, task.duration_minutes)

        # --- Emit suggestions from each free interval ---
        for interval_start, interval_end in free:
            if len(suggestions) >= MAX_SUGGESTIONS:
                break

            # Walk through the free interval emitting non-overlapping slots
            slot_start = interval_start
            while slot_start + duration <= interval_end:
                if len(suggestions) >= MAX_SUGGESTIONS:
                    break

                slot_end = slot_start + duration

                # Enforce deadline ceiling (inclusive)
                if deadline_ceiling is not None and slot_end > deadline_ceiling:
                    break

                suggestions.append(
                    SlotSuggestion(
                        start_datetime=slot_start,
                        end_datetime=slot_end,
                        date=day,
                    )
                )
                # Advance to next non-overlapping slot within this free interval
                slot_start = slot_end

    return suggestions
