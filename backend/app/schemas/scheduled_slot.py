from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ScheduledSlotRead(BaseModel):
    """Response schema — maps directly from the ORM model.

    There is no Create schema here: slot creation is handled exclusively
    through BookRequest in schemas/engine.py (POST /engine/book).
    end_datetime is always computed server-side as start_datetime + task.duration_minutes.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    user_id: int
    start_datetime: datetime
    end_datetime: datetime
    created_at: datetime
