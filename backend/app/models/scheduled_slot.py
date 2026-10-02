from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ScheduledSlot(Base):
    __tablename__ = "scheduled_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # UNIQUE enforces one active slot per task in Week 1 MVP
    task_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    start_datetime: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # Always computed server-side as start_datetime + task.duration_minutes
    end_datetime: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    task: Mapped["Task"] = relationship(  # noqa: F821
        "Task", back_populates="scheduled_slot"
    )

    __table_args__ = (
        CheckConstraint("end_datetime > start_datetime", name="ck_scheduled_slots_datetime_order"),
        # Explicit index on (user_id, start_datetime) for engine range queries
        Index("ix_scheduled_slots_user_start", "user_id", "start_datetime"),
    )
