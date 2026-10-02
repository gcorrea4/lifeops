import enum


class RecurrenceType(str, enum.Enum):
    weekly = "weekly"
    once = "once"


class Priority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class TaskStatus(str, enum.Enum):
    pending = "pending"
    scheduled = "scheduled"
    done = "done"
