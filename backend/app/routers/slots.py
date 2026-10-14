"""ScheduledSlot read and delete router.

Slot creation is intentionally absent — it is reserved for POST /engine/book (ST-5).
DELETE atomically resets the related task's status to pending within the same transaction.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.session import current_user_id
from app.database import get_db
from app.models.enums import TaskStatus
from app.models.scheduled_slot import ScheduledSlot
from app.schemas.scheduled_slot import ScheduledSlotRead

router = APIRouter(prefix="/slots", tags=["slots"])


def _get_slot_or_404(slot_id: int, user_id: int, db: Session) -> ScheduledSlot:
    slot = db.query(ScheduledSlot).filter(
        ScheduledSlot.id == slot_id,
        ScheduledSlot.user_id == user_id,
    ).first()
    if slot is None:
        raise HTTPException(status_code=404, detail=f"Scheduled slot {slot_id} not found")
    return slot


@router.get("/", response_model=List[ScheduledSlotRead])
def list_slots(
    db: Session = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> List[ScheduledSlot]:
    return db.query(ScheduledSlot).filter(ScheduledSlot.user_id == user_id).all()


@router.get("/{slot_id}", response_model=ScheduledSlotRead)
def get_slot(
    slot_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> ScheduledSlot:
    return _get_slot_or_404(slot_id, user_id, db)


@router.delete("/{slot_id}", status_code=204)
def delete_slot(
    slot_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> None:
    slot = _get_slot_or_404(slot_id, user_id, db)

    # Reset the related task to pending — must happen before db.delete so the
    # relationship is still accessible.
    slot.task.status = TaskStatus.pending
    db.add(slot.task)

    db.delete(slot)

    # Single commit: both the status reset and the slot deletion are atomic.
    db.commit()
