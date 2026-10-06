"""
SQLAlchemy ORM model for the ai_recommendations audit table.

One row is created per POST /planner/recommend call.
The row is updated in-place when the user records a decision
via POST /planner/decision.

Sensitive data (raw completions, chain-of-thought) is never stored here.
"""

from __future__ import annotations

import enum

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserAction(str, enum.Enum):
    APPROVED = "APPROVED"
    MODIFIED = "MODIFIED"
    REJECTED = "REJECTED"


class AIRecommendation(Base):
    __tablename__ = "ai_recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # --- Task reference ---
    task_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # --- Metadata ---
    created_at: Mapped[DateTime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)

    # --- Candidate slots (full JSON array stored for MODIFIED validation) ---
    candidate_slots_json: Mapped[str] = mapped_column(Text, nullable=False)

    # --- Agent recommendation ---
    recommended_start: Mapped[DateTime] = mapped_column(DateTime, nullable=True)
    recommended_end: Mapped[DateTime] = mapped_column(DateTime, nullable=True)
    reason_codes: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    fallback_used: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # --- Human decision (populated by POST /planner/decision) ---
    user_action: Mapped[str] = mapped_column(
        SAEnum(UserAction, name="useraction"), nullable=True
    )
    # The slot the user ultimately chose to send to /engine/book
    final_start: Mapped[DateTime] = mapped_column(DateTime, nullable=True)
    final_end: Mapped[DateTime] = mapped_column(DateTime, nullable=True)
