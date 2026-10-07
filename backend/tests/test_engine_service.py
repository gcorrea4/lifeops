"""Unit tests for app.services.engine — pure functions, no database.

Each test constructs plain Python objects (FixedBlock / ScheduledSlot instances
or simple Interval tuples) and exercises one function at a time.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models.enums import RecurrenceType
from app.models.fixed_block import FixedBlock
from app.models.scheduled_slot import ScheduledSlot
from app.services.engine import (
    block_to_interval,
    blocks_for_day,
    compute_free_intervals,
    filter_by_duration,
    merge_intervals,
    overnight_blocks_from_previous_day,
    overnight_tail_interval,
    slots_to_intervals,
    suggest_slots,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MONDAY = date(2025, 7, 7)   # weekday() == 0
TUESDAY = date(2025, 7, 8)  # weekday() == 1

WORK_START = time(8, 0)
WORK_END = time(22, 0)


def _dt(d: date, h: int, m: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, h, m)


def _weekly_block(
    weekday: int,
    start_h: int,
    end_h: int,
    spans_next_day: bool = False,
    start_m: int = 0,
    end_m: int = 0,
) -> FixedBlock:
    block = MagicMock(spec=FixedBlock)
    block.recurrence_type = RecurrenceType.weekly
    block.weekday = weekday
    block.date = None
    block.start_time = time(start_h, start_m)
    block.end_time = time(end_h, end_m)
    block.spans_next_day = spans_next_day
    return block


def _once_block(
    d: date,
    start_h: int,
    end_h: int,
    spans_next_day: bool = False,
    start_m: int = 0,
    end_m: int = 0,
) -> FixedBlock:
    block = MagicMock(spec=FixedBlock)
    block.recurrence_type = RecurrenceType.once
    block.weekday = None
    block.date = d
    block.start_time = time(start_h, start_m)
    block.end_time = time(end_h, end_m)
    block.spans_next_day = spans_next_day
    return block


def _task(duration_minutes: int, deadline: date | None = None) -> object:
    return SimpleNamespace(duration_minutes=duration_minutes, deadline=deadline)


def _slot(start: datetime, end: datetime) -> ScheduledSlot:
    s = MagicMock(spec=ScheduledSlot)
    s.start_datetime = start
    s.end_datetime = end
    return s


# ---------------------------------------------------------------------------
# merge_intervals
# ---------------------------------------------------------------------------


def test_merge_empty():
    assert merge_intervals([]) == []


def test_merge_no_overlap():
    iv = [
        (_dt(MONDAY, 9), _dt(MONDAY, 10)),
        (_dt(MONDAY, 11), _dt(MONDAY, 12)),
    ]
    result = merge_intervals(iv)
    assert result == [
        (_dt(MONDAY, 9), _dt(MONDAY, 10)),
        (_dt(MONDAY, 11), _dt(MONDAY, 12)),
    ]


def test_merge_overlapping():
    iv = [
        (_dt(MONDAY, 9), _dt(MONDAY, 10, 30)),
        (_dt(MONDAY, 10), _dt(MONDAY, 11)),
    ]
    result = merge_intervals(iv)
    assert result == [(_dt(MONDAY, 9), _dt(MONDAY, 11))]


def test_merge_adjacent():
    """Adjacent intervals (end == start of next) ARE merged per plan rule."""
    iv = [
        (_dt(MONDAY, 9), _dt(MONDAY, 10)),
        (_dt(MONDAY, 10), _dt(MONDAY, 11)),
    ]
    result = merge_intervals(iv)
    assert result == [(_dt(MONDAY, 9), _dt(MONDAY, 11))]


def test_merge_contained():
    """Inner interval fully contained within outer collapses to outer."""
    iv = [
        (_dt(MONDAY, 9), _dt(MONDAY, 13)),
        (_dt(MONDAY, 10), _dt(MONDAY, 11)),
    ]
    result = merge_intervals(iv)
    assert result == [(_dt(MONDAY, 9), _dt(MONDAY, 13))]


def test_merge_out_of_order_input():
    """Input order does not matter — result is always sorted and merged."""
    iv = [
        (_dt(MONDAY, 11), _dt(MONDAY, 12)),
        (_dt(MONDAY, 9), _dt(MONDAY, 10)),
    ]
    result = merge_intervals(iv)
    assert result == [
        (_dt(MONDAY, 9), _dt(MONDAY, 10)),
        (_dt(MONDAY, 11), _dt(MONDAY, 12)),
    ]


# ---------------------------------------------------------------------------
# compute_free_intervals
# ---------------------------------------------------------------------------


def test_free_intervals_empty_occupied():
    """No occupied intervals → full working window is free."""
    free = compute_free_intervals([], WORK_START, WORK_END, MONDAY)
    assert free == [(_dt(MONDAY, 8), _dt(MONDAY, 22))]


def test_free_intervals_full_day_blocked():
    """Occupied spans entire working window → no free intervals."""
    occupied = [(_dt(MONDAY, 8), _dt(MONDAY, 22))]
    free = compute_free_intervals(occupied, WORK_START, WORK_END, MONDAY)
    assert free == []


def test_free_intervals_partial_overlap_start():
    """Occupied block at the start of the window leaves a gap at the end."""
    occupied = [(_dt(MONDAY, 8), _dt(MONDAY, 12))]
    free = compute_free_intervals(occupied, WORK_START, WORK_END, MONDAY)
    assert free == [(_dt(MONDAY, 12), _dt(MONDAY, 22))]


def test_free_intervals_partial_overlap_end():
    """Occupied block at the end leaves a gap at the start."""
    occupied = [(_dt(MONDAY, 18), _dt(MONDAY, 22))]
    free = compute_free_intervals(occupied, WORK_START, WORK_END, MONDAY)
    assert free == [(_dt(MONDAY, 8), _dt(MONDAY, 18))]


def test_free_intervals_multiple_gaps():
    """Two occupied blocks produce two free gaps."""
    occupied = [
        (_dt(MONDAY, 9), _dt(MONDAY, 10)),
        (_dt(MONDAY, 12), _dt(MONDAY, 14)),
    ]
    free = compute_free_intervals(occupied, WORK_START, WORK_END, MONDAY)
    assert free == [
        (_dt(MONDAY, 8), _dt(MONDAY, 9)),
        (_dt(MONDAY, 10), _dt(MONDAY, 12)),
        (_dt(MONDAY, 14), _dt(MONDAY, 22)),
    ]


def test_free_intervals_occupied_outside_window_ignored():
    """Occupied intervals wholly outside the working window are ignored."""
    occupied = [
        (_dt(MONDAY, 0), _dt(MONDAY, 7)),   # before window
        (_dt(MONDAY, 23), _dt(TUESDAY, 1)),  # after window
    ]
    free = compute_free_intervals(occupied, WORK_START, WORK_END, MONDAY)
    assert free == [(_dt(MONDAY, 8), _dt(MONDAY, 22))]


# ---------------------------------------------------------------------------
# filter_by_duration
# ---------------------------------------------------------------------------


def test_filter_by_duration_exact_fit():
    """Interval exactly fitting the duration is kept."""
    iv = [(_dt(MONDAY, 9), _dt(MONDAY, 10))]  # 60 minutes
    result = filter_by_duration(iv, 60)
    assert result == iv


def test_filter_by_duration_too_short():
    """Interval shorter than required duration is dropped."""
    iv = [(_dt(MONDAY, 9), _dt(MONDAY, 9, 30))]  # 30 minutes
    result = filter_by_duration(iv, 60)
    assert result == []


def test_filter_by_duration_mix():
    """Only intervals that fit are retained."""
    iv = [
        (_dt(MONDAY, 9), _dt(MONDAY, 9, 30)),   # 30 min — too short
        (_dt(MONDAY, 10), _dt(MONDAY, 12)),      # 120 min — fits
    ]
    result = filter_by_duration(iv, 60)
    assert result == [(_dt(MONDAY, 10), _dt(MONDAY, 12))]


# ---------------------------------------------------------------------------
# blocks_for_day
# ---------------------------------------------------------------------------


def test_blocks_for_day_weekly_match():
    block = _weekly_block(weekday=MONDAY.weekday(), start_h=9, end_h=10)
    result = blocks_for_day([block], MONDAY)
    assert block in result


def test_blocks_for_day_weekly_no_match():
    block = _weekly_block(weekday=TUESDAY.weekday(), start_h=9, end_h=10)
    result = blocks_for_day([block], MONDAY)
    assert result == []


def test_blocks_for_day_once_match():
    block = _once_block(d=MONDAY, start_h=9, end_h=10)
    result = blocks_for_day([block], MONDAY)
    assert block in result


def test_blocks_for_day_once_no_match():
    block = _once_block(d=TUESDAY, start_h=9, end_h=10)
    result = blocks_for_day([block], MONDAY)
    assert result == []


# ---------------------------------------------------------------------------
# overnight_blocks_from_previous_day
# ---------------------------------------------------------------------------


def test_overnight_from_previous_day():
    """A weekly block with spans_next_day on Monday should appear for Tuesday."""
    block = _weekly_block(
        weekday=MONDAY.weekday(), start_h=22, end_h=6, spans_next_day=True
    )
    result = overnight_blocks_from_previous_day([block], TUESDAY)
    assert block in result


def test_overnight_from_previous_day_not_spans():
    """A block without spans_next_day should NOT appear as previous-day overflow."""
    block = _weekly_block(weekday=MONDAY.weekday(), start_h=9, end_h=10, spans_next_day=False)
    result = overnight_blocks_from_previous_day([block], TUESDAY)
    assert result == []


def test_overnight_from_previous_day_once():
    """A once block with spans_next_day appears as previous-day overflow on next date."""
    block = _once_block(d=MONDAY, start_h=22, end_h=6, spans_next_day=True)
    result = overnight_blocks_from_previous_day([block], TUESDAY)
    assert block in result


# ---------------------------------------------------------------------------
# block_to_interval and overnight_tail_interval
# ---------------------------------------------------------------------------


def test_block_to_interval_normal():
    block = _once_block(d=MONDAY, start_h=9, end_h=11)
    interval = block_to_interval(block, MONDAY)
    assert interval == (_dt(MONDAY, 9), _dt(MONDAY, 11))


def test_block_to_interval_overnight_origin():
    """Overnight block's origin interval ends at midnight of next day."""
    block = _once_block(d=MONDAY, start_h=22, end_h=6, spans_next_day=True)
    interval = block_to_interval(block, MONDAY)
    midnight_tuesday = datetime(TUESDAY.year, TUESDAY.month, TUESDAY.day, 0, 0)
    assert interval == (_dt(MONDAY, 22), midnight_tuesday)


def test_overnight_tail_interval_value():
    """Tail interval starts at midnight of the continuation day."""
    block = _weekly_block(weekday=MONDAY.weekday(), start_h=22, end_h=6, spans_next_day=True)
    interval = overnight_tail_interval(block, TUESDAY)
    midnight_tuesday = datetime(TUESDAY.year, TUESDAY.month, TUESDAY.day, 0, 0)
    assert interval == (midnight_tuesday, _dt(TUESDAY, 6))


# ---------------------------------------------------------------------------
# slots_to_intervals
# ---------------------------------------------------------------------------


def test_slots_to_intervals_same_day():
    slot = _slot(_dt(MONDAY, 10), _dt(MONDAY, 12))
    result = slots_to_intervals([slot], MONDAY)
    assert result == [(_dt(MONDAY, 10), _dt(MONDAY, 12))]


def test_slots_to_intervals_other_day_excluded():
    slot = _slot(_dt(TUESDAY, 10), _dt(TUESDAY, 12))
    result = slots_to_intervals([slot], MONDAY)
    assert result == []


# ---------------------------------------------------------------------------
# suggest_slots — integration of all pure functions
# ---------------------------------------------------------------------------


def test_suggest_empty_schedule():
    """No blocks and no slots → slots are suggested across the lookahead window."""
    task = _task(duration_minutes=60)
    result = suggest_slots(task, [], [], MONDAY, lookahead_days=2,
                           work_start=WORK_START, work_end=WORK_END, now=_dt(MONDAY, 7))
    assert len(result) > 0
    # All returned slots start on or after MONDAY
    for s in result:
        assert s.start_datetime.date() >= MONDAY
    # Ordered by start_datetime ascending
    starts = [s.start_datetime for s in result]
    assert starts == sorted(starts)


def test_suggest_full_day_blocked():
    """A block covering the full working window leaves no free time on that day."""
    block = _once_block(d=MONDAY, start_h=8, end_h=22)
    task = _task(duration_minutes=60)
    result = suggest_slots(task, [block], [], MONDAY, lookahead_days=1,
                           work_start=WORK_START, work_end=WORK_END, now=_dt(MONDAY, 7))
    monday_slots = [s for s in result if s.date == MONDAY]
    assert monday_slots == []


def test_suggest_overnight_block_origin_day():
    """Overnight block occupies the tail of its origin day."""
    # Block: Monday 20:00 → Tuesday 06:00
    block = _once_block(d=MONDAY, start_h=20, end_h=6, spans_next_day=True)
    task = _task(duration_minutes=60)
    result = suggest_slots(task, [block], [], MONDAY, lookahead_days=1,
                           work_start=WORK_START, work_end=WORK_END, now=_dt(MONDAY, 7))
    # No slot on Monday should start at or after 20:00
    for s in result:
        if s.date == MONDAY:
            assert s.start_datetime.hour < 20


def test_suggest_overnight_block_next_day():
    """Overnight block's tail occupies the start of the next day."""
    # Block: Monday 22:00 → Tuesday 10:00 (spans_next_day)
    block = _once_block(d=MONDAY, start_h=22, end_h=10, spans_next_day=True)
    task = _task(duration_minutes=60)
    result = suggest_slots(task, [block], [], TUESDAY, lookahead_days=1,
                           work_start=WORK_START, work_end=WORK_END, now=_dt(MONDAY, 7))
    # On Tuesday no slot should start before 10:00
    for s in result:
        if s.date == TUESDAY:
            assert s.start_datetime.hour >= 10


def test_suggest_overlapping_blocks():
    """Two overlapping blocks on the same day merge into one occupied span."""
    b1 = _once_block(d=MONDAY, start_h=9, end_h=11)
    b2 = _once_block(d=MONDAY, start_h=10, end_h=12)
    task = _task(duration_minutes=60)
    result = suggest_slots(task, [b1, b2], [], MONDAY, lookahead_days=1,
                           work_start=WORK_START, work_end=WORK_END, now=_dt(MONDAY, 7))
    # No slot should overlap [09:00, 12:00)
    for s in result:
        if s.date == MONDAY:
            assert not (s.start_datetime < _dt(MONDAY, 12) and
                        s.end_datetime > _dt(MONDAY, 9))


def test_suggest_adjacent_blocks_merged():
    """Two adjacent blocks (end==start) are merged; no slot in combined span."""
    b1 = _once_block(d=MONDAY, start_h=9, end_h=10)
    b2 = _once_block(d=MONDAY, start_h=10, end_h=11)
    task = _task(duration_minutes=60)
    result = suggest_slots(task, [b1, b2], [], MONDAY, lookahead_days=1,
                           work_start=WORK_START, work_end=WORK_END, now=_dt(MONDAY, 7))
    # No slot should start between 09:00 and 11:00 on Monday
    for s in result:
        if s.date == MONDAY:
            assert not (_dt(MONDAY, 9) <= s.start_datetime < _dt(MONDAY, 11))


def test_suggest_deadline_filters_slots_after_deadline():
    """Slots that start after the deadline day are not suggested."""
    deadline = MONDAY
    task = _task(duration_minutes=60, deadline=deadline)
    result = suggest_slots(task, [], [], MONDAY, lookahead_days=7,
                           work_start=WORK_START, work_end=WORK_END, now=_dt(MONDAY, 7))
    for s in result:
        assert s.date <= deadline


def test_suggest_deadline_boundary_slot_fits():
    """A slot ending exactly at WORK_END on the deadline day IS included.

    Block most of the day so only a single 60-minute window remains at the end
    (21:00–22:00).  That slot ends exactly at WORK_END and must be returned even
    though the deadline is on the same day.
    """
    deadline = TUESDAY

    # Block 08:00–21:00 — leaves only 21:00–22:00 free
    block = _once_block(d=deadline, start_h=8, end_h=21)
    task = _task(duration_minutes=60, deadline=deadline)
    result = suggest_slots(task, [block], [], deadline, lookahead_days=1,
                           work_start=WORK_START, work_end=WORK_END, now=_dt(MONDAY, 7))
    # The only candidate is 21:00–22:00; end_datetime == WORK_END must be included
    deadline_dt_end = datetime.combine(deadline, WORK_END)
    ends_at_work_end = [s for s in result
                        if s.end_datetime == deadline_dt_end and s.date == deadline]
    assert len(ends_at_work_end) == 1


def test_suggest_deadline_boundary_slot_too_long():
    """A slot that would end AFTER WORK_END on the deadline day is NOT included."""
    deadline = MONDAY
    # 90-minute task; if slot starts at 21:00 it ends at 22:30 — must be rejected
    task = _task(duration_minutes=90, deadline=deadline)
    result = suggest_slots(task, [], [], MONDAY, lookahead_days=1,
                           work_start=WORK_START, work_end=WORK_END, now=_dt(MONDAY, 7))
    for s in result:
        assert s.end_datetime <= _dt(MONDAY, 22)


def test_suggest_task_fits_exactly():
    """Task duration exactly fills the remaining free interval."""
    # Block covers 08:00–20:00; only a 2-hour window remains (20:00–22:00)
    block = _once_block(d=MONDAY, start_h=8, end_h=20)
    task = _task(duration_minutes=120)
    result = suggest_slots(task, [block], [], MONDAY, lookahead_days=1,
                           work_start=WORK_START, work_end=WORK_END, now=_dt(MONDAY, 7))
    monday_slots = [s for s in result if s.date == MONDAY]
    assert len(monday_slots) == 1
    assert monday_slots[0].start_datetime == _dt(MONDAY, 20)
    assert monday_slots[0].end_datetime == _dt(MONDAY, 22)


def test_suggest_max_10_suggestions():
    """Never returns more than 10 suggestions."""
    task = _task(duration_minutes=30)  # many slots fit in 7 days
    result = suggest_slots(task, [], [], MONDAY, lookahead_days=7,
                           work_start=WORK_START, work_end=WORK_END, now=_dt(MONDAY, 7))
    assert len(result) <= 10


def test_suggest_existing_slot_blocks_time():
    """An existing ScheduledSlot occupies its interval and prevents overlap."""
    slot = _slot(_dt(MONDAY, 9), _dt(MONDAY, 11))
    task = _task(duration_minutes=60)
    result = suggest_slots(task, [], [slot], MONDAY, lookahead_days=1,
                           work_start=WORK_START, work_end=WORK_END, now=_dt(MONDAY, 7))
    for s in result:
        if s.date == MONDAY:
            # No suggested slot should overlap [09:00, 11:00)
            assert not (s.start_datetime < _dt(MONDAY, 11) and
                        s.end_datetime > _dt(MONDAY, 9))


@pytest.mark.parametrize("hour,minute,first_day,first_hour", [
    (7, 0, MONDAY, 8),
    (15, 30, MONDAY, 16),
    (15, 0, MONDAY, 16),
    (21, 0, TUESDAY, 8),
    (22, 0, TUESDAY, 8),
    (23, 0, TUESDAY, 8),
])
def test_suggest_explicit_cutoff(hour, minute, first_day, first_hour):
    now = _dt(MONDAY, hour, minute)
    result = suggest_slots(_task(60), [], [], MONDAY, 2,
                           WORK_START, WORK_END, now=now)
    assert result[0].start_datetime == _dt(first_day, first_hour)
    assert all(s.start_datetime > now for s in result)
    assert all(s.end_datetime - s.start_datetime == timedelta(minutes=60)
               for s in result)
    assert len(result) == 10
    assert [s.start_datetime for s in result] == sorted(s.start_datetime for s in result)


def test_suggest_future_day_unchanged():
    early = suggest_slots(_task(60), [], [], TUESDAY, 1,
                          WORK_START, WORK_END, now=_dt(MONDAY, 7))
    late = suggest_slots(_task(60), [], [], TUESDAY, 1,
                         WORK_START, WORK_END, now=_dt(MONDAY, 23))
    assert early == late
    assert early[0].start_datetime == _dt(TUESDAY, 8)


def test_suggest_deadline_today_no_remaining_fit():
    assert suggest_slots(_task(60, deadline=MONDAY), [], [], MONDAY, 7,
                         WORK_START, WORK_END, now=_dt(MONDAY, 21, 30)) == []


def test_suggest_cutoff_keeps_conflicts_and_overnight_tail():
    tail = _once_block(MONDAY, 22, 10, spans_next_day=True)
    slot = _slot(_dt(TUESDAY, 11), _dt(TUESDAY, 13))
    result = suggest_slots(_task(60), [tail], [slot], TUESDAY, 1,
                           WORK_START, WORK_END, now=_dt(TUESDAY, 9, 30))
    assert result[0].start_datetime == _dt(TUESDAY, 10)
    assert all(not (s.start_datetime < _dt(TUESDAY, 13)
                    and s.end_datetime > _dt(TUESDAY, 11)) for s in result)
    assert all(s.end_datetime <= _dt(TUESDAY, 22) for s in result)
