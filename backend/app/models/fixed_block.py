from datetime import date, datetime, time

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Enum, Index, Integer, SmallInteger, String, Time, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import RecurrenceType


class FixedBlock(Base):
    __tablename__ = "fixed_blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    recurrence_type: Mapped[RecurrenceType] = mapped_column(
        Enum(RecurrenceType, name="recurrencetype"), nullable=False
    )
    # Mutually exclusive: weekday is set for weekly, date is set for once
    weekday: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    date: Mapped[date | None] = mapped_column(Date, nullable=True)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    # True when the block crosses midnight (e.g. 18:00 → 06:00 next day)
    spans_next_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        # weekday must be in 0–6 when provided
        CheckConstraint("weekday IS NULL OR weekday BETWEEN 0 AND 6", name="ck_fixed_blocks_weekday_range"),
        # mutual exclusivity: weekly ↔ weekday set; once ↔ date set
        CheckConstraint(
            "(recurrence_type = 'weekly' AND weekday IS NOT NULL AND date IS NULL) OR "
            "(recurrence_type = 'once'   AND date IS NOT NULL AND weekday IS NULL)",
            name="ck_fixed_blocks_recurrence_fields",
        ),
        # Performance indexes for the availability engine
        Index("ix_fixed_blocks_user_recurrence", "user_id", "recurrence_type"),
        Index("ix_fixed_blocks_user_date", "user_id", "date"),
    )
