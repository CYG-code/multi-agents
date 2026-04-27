from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_current_user, require_teacher
from app.models.room import Room, RoomStatus
from app.models.user import User
from app.schemas.task import TaskCreate, TaskResponse, TaskUpdate
from app.services import task_service

router = APIRouter()


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    tasks = await task_service.list_tasks(db)
    return [TaskResponse.model_validate(t) for t in tasks]


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(
    data: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    task = await task_service.create_task(db, data, current_user.id)
    return TaskResponse.model_validate(task)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    task = await task_service.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse.model_validate(task)


@router.patch("/{task_id}", response_model=TaskResponse)
async def patch_task(
    task_id: UUID,
    data: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_teacher),
):
    task = await task_service.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task = await task_service.update_task(db, task, data)
    return TaskResponse.model_validate(task)


@router.delete("/{task_id}", status_code=200)
async def delete_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_teacher),
):
    task = await task_service.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    in_use = await db.execute(
        select(Room.id).where(Room.task_id == task_id, Room.status != RoomStatus.ended).limit(1)
    )
    if in_use.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Task is used by an active room")

    await task_service.delete_task(db, task_id)
    return {"detail": "Task deleted"}
