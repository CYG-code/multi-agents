from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.schemas.task import TaskCreate, TaskUpdate


async def list_tasks(db: AsyncSession) -> list[Task]:
    result = await db.execute(select(Task))
    return list(result.scalars().all())


async def create_task(db: AsyncSession, data: TaskCreate, created_by: UUID) -> Task:
    task = Task(**data.model_dump(), created_by=created_by)
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def get_task(db: AsyncSession, task_id: UUID) -> Task | None:
    result = await db.execute(select(Task).where(Task.id == task_id))
    return result.scalar_one_or_none()


async def update_task(db: AsyncSession, task: Task, data: TaskUpdate) -> Task:
    patch = data.model_dump(exclude_unset=True)
    for key, value in patch.items():
        setattr(task, key, value)

    await db.commit()
    await db.refresh(task)
    return task


async def delete_task(db: AsyncSession, task_id: UUID) -> None:
    await db.execute(delete(Task).where(Task.id == task_id))
    await db.commit()
