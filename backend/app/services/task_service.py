from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.schemas.task import TaskCreate


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

