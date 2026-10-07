"""Shared wall clock; scheduling services receive explicit time values."""

from datetime import datetime


def now() -> datetime:
    """Return the current naive local datetime."""
    return datetime.now()
