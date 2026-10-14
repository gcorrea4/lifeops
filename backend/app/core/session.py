"""Per-visitor data separation for the public demo.

There is no login. The browser sends a random identifier in the X-Session-Id header and the API
maps it to a numeric user_id, so every visitor only sees their own tasks, commitments, slots and
recommendations. This separates data for a demo; it is NOT authentication: whoever knows an
identifier can use it.

Requests without the header keep using DEFAULT_USER_ID (local development, tests and direct API
clients), which is exempt from cleanup and from the daily recommendation limit.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
from datetime import datetime, timedelta, timezone

from fastapi import Header, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.ai_recommendation import AIRecommendation
from app.models.fixed_block import FixedBlock
from app.models.task import Task

logger = logging.getLogger(__name__)

DEFAULT_USER_ID = 1
SESSION_TTL_HOURS = 24
DAILY_RECOMMENDATION_LIMIT = 10
PURGE_INTERVAL = timedelta(minutes=30)
RATE_LIMIT_DETAIL = "daily recommendation limit reached"

_SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
_purge_lock = threading.Lock()
_last_purge: datetime | None = None


def user_id_from_session(session_id: str) -> int:
    """Stable positive 31-bit user id for a session identifier; never equals DEFAULT_USER_ID."""
    digest = hashlib.sha256(session_id.encode("utf-8")).digest()
    return 2 + int.from_bytes(digest[:4], "big") % (2**31 - 3)


def current_user_id(x_session_id: str | None = Header(default=None)) -> int:
    """FastAPI dependency: the user id of the caller."""
    if not x_session_id:
        return DEFAULT_USER_ID
    if not _SESSION_ID_PATTERN.match(x_session_id):
        raise HTTPException(status_code=400, detail="invalid session id")
    return user_id_from_session(x_session_id)


def _utc_now() -> datetime:
    """Naive UTC time; created_at columns are filled by the database in UTC."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def purge_expired(db: Session, now: datetime | None = None, force: bool = False) -> int:
    """Delete visitor data older than SESSION_TTL_HOURS (never the default user's).

    Runs lazily, at most once per PURGE_INTERVAL per process, when data is created. Slots and
    recommendations go with their tasks through the database ON DELETE CASCADE. Failures are
    logged and never block the request. Returns the number of deleted tasks and commitments.
    """
    global _last_purge
    current = now or _utc_now()
    with _purge_lock:
        if not force and _last_purge is not None and current - _last_purge < PURGE_INTERVAL:
            return 0
        _last_purge = current
    cutoff = current - timedelta(hours=SESSION_TTL_HOURS)
    deleted = 0
    try:
        for model in (Task, FixedBlock):
            deleted += (
                db.query(model)
                .filter(model.user_id != DEFAULT_USER_ID, model.created_at < cutoff)
                .delete(synchronize_session=False)
            )
        db.commit()
    except Exception:  # noqa: BLE001 - cleanup must never break the request
        db.rollback()
        logger.exception("expired session data purge failed")
        return 0
    return deleted


def enforce_recommendation_limit(db: Session, user_id: int, now: datetime | None = None) -> None:
    """Raise 429 when a visitor already asked for DAILY_RECOMMENDATION_LIMIT recommendations today."""
    if user_id == DEFAULT_USER_ID:
        return
    since = (now or _utc_now()) - timedelta(hours=24)
    used = (
        db.query(func.count(AIRecommendation.id))
        .filter(AIRecommendation.user_id == user_id, AIRecommendation.created_at >= since)
        .scalar()
    )
    if used >= DAILY_RECOMMENDATION_LIMIT:
        raise HTTPException(status_code=429, detail=RATE_LIMIT_DETAIL)
