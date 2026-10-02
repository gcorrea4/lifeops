"""Task CRUD router."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.enums import TaskStatus
from app.models.task import Task
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate
from app.services.task import apply_patch

router = APIRouter(prefix="/tasks", tags=["tasks"])

USER_ID = 1  # hardcoded for Week 1 MVP


def _get_task_or_404(task_id: int, db: Session) -> Task:
    task = db.query(Task).filter(
        Task.id == task_id,
        Task.user_id == USER_ID,
    ).first()
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task


@router.post("/", response_model=TaskRead, status_code=201)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)) -> Task:
    task_data = payload.model_dump()
    task = Task(
        user_id=USER_ID,
        status=TaskStatus.pending,
        **task_data,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.get("/", response_model=List[TaskRead])
def list_tasks(
    status: Optional[TaskStatus] = Query(None),
    db: Session = Depends(get_db),
) -> List[Task]:
    query = db.query(Task).filter(Task.user_id == USER_ID)
    if status is not None:
        query = query.filter(Task.status == status)
    return query.all()


@router.get("/{task_id}", response_model=TaskRead)
def get_task(task_id: int, db: Session = Depends(get_db)) -> Task:
    return _get_task_or_404(task_id, db)


@router.patch("/{task_id}", response_model=TaskRead)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    db: Session = Depends(get_db),
) -> Task:
    task = _get_task_or_404(task_id, db)
    apply_patch(task, payload)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: int, db: Session = Depends(get_db)) -> None:
    task = _get_task_or_404(task_id, db)
    db.delete(task)
    db.commit()
