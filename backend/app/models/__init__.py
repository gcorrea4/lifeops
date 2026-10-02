# Import all models here so that Base.metadata is fully populated
# before create_all is called at startup.
from app.models.fixed_block import FixedBlock
from app.models.scheduled_slot import ScheduledSlot
from app.models.task import Task

__all__ = ["FixedBlock", "Task", "ScheduledSlot"]
