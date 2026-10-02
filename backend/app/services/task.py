"""Application-layer service functions for Task."""

from datetime import date

from fastapi import HTTPException

from app.models.task import Task
from app.schemas.task import TaskUpdate


def apply_patch(db_task: Task, payload: TaskUpdate) -> Task:
    """Apply payload fields onto db_task.

    Conditional deadline rule:
    - If the client explicitly sends a new deadline value, it must not be in the past.
    - If the PATCH body does not include 'deadline', the stored deadline is never
      re-evaluated — a task that became overdue simply remains valid.

    status is never touched by this function.
    """
    candidate = payload.model_dump(exclude_unset=True)

    if "deadline" in candidate:
        new_deadline = candidate["deadline"]
        if new_deadline is not None and new_deadline < date.today():
            raise HTTPException(
                status_code=422,
                detail="deadline must be today or in the future",
            )

    for field, value in candidate.items():
        setattr(db_task, field, value)

    return db_task
