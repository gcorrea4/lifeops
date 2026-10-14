"""FixedBlock CRUD router."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.session import current_user_id, purge_expired
from app.database import get_db
from app.models.fixed_block import FixedBlock
from app.schemas.fixed_block import FixedBlockCreate, FixedBlockRead, FixedBlockUpdate
from app.services.fixed_block import (
    apply_patch,
    compute_spans_next_day,
    validate_recurrence,
    validate_time_range,
)

router = APIRouter(prefix="/blocks", tags=["blocks"])


def _get_block_or_404(block_id: int, user_id: int, db: Session) -> FixedBlock:
    block = db.query(FixedBlock).filter(
        FixedBlock.id == block_id,
        FixedBlock.user_id == user_id,
    ).first()
    if block is None:
        raise HTTPException(status_code=404, detail=f"Fixed block {block_id} not found")
    return block


@router.post("/", response_model=FixedBlockRead, status_code=201)
def create_block(
    payload: FixedBlockCreate,
    db: Session = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> FixedBlock:
    purge_expired(db)
    candidate: dict = payload.model_dump()
    # Enforce recurrence mutual exclusivity and time validity on creation too
    validate_recurrence(candidate)
    validate_time_range(candidate)
    candidate["spans_next_day"] = compute_spans_next_day(candidate)
    candidate["user_id"] = user_id

    block = FixedBlock(**candidate)
    db.add(block)
    db.commit()
    db.refresh(block)
    return block


@router.get("/", response_model=List[FixedBlockRead])
def list_blocks(
    db: Session = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> List[FixedBlock]:
    return db.query(FixedBlock).filter(FixedBlock.user_id == user_id).all()


@router.get("/{block_id}", response_model=FixedBlockRead)
def get_block(
    block_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> FixedBlock:
    return _get_block_or_404(block_id, user_id, db)


@router.patch("/{block_id}", response_model=FixedBlockRead)
def update_block(
    block_id: int,
    payload: FixedBlockUpdate,
    db: Session = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> FixedBlock:
    block = _get_block_or_404(block_id, user_id, db)
    apply_patch(block, payload)
    db.add(block)
    db.commit()
    db.refresh(block)
    return block


@router.delete("/{block_id}", status_code=204)
def delete_block(
    block_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> None:
    block = _get_block_or_404(block_id, user_id, db)
    db.delete(block)
    db.commit()
