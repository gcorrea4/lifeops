from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Enum, Index, Integer, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import Priority, TaskStatus


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    priority: Mapped[Priority] = mapped_column(
        Enum(Priority, name="priority"), nullable=False, default=Priority.medium
    )
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="taskstatus"), nullable=False, default=TaskStatus.pending
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    # Relationship: a task has at most one scheduled slot (enforced by UNIQUE on task_id)
    scheduled_slot: Mapped["ScheduledSlot"] = relationship(  # noqa: F821
        "ScheduledSlot", back_populates="task", uselist=False
    )

    __table_args__ = (
        CheckConstraint("duration_minutes > 0", name="ck_tasks_duration_positive"),
        Index("ix_tasks_user_status", "user_id", "status"),
    )
