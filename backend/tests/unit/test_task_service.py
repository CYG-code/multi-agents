import uuid

import pytest

from app.models.task import Task
from app.schemas.task import TaskCreate
from app.services import task_service
from tests.conftest import FakeExecuteResult


@pytest.mark.asyncio
async def test_list_tasks_returns_scalars(fake_db):
    t1 = Task(title="任务1", created_by=uuid.uuid4())
    t2 = Task(title="任务2", created_by=uuid.uuid4())
    fake_db.execute_result = FakeExecuteResult(scalar_list=[t1, t2])

    result = await task_service.list_tasks(fake_db)

    assert len(result) == 2
    assert result[0].title == "任务1"


@pytest.mark.asyncio
async def test_create_task(fake_db):
    creator_id = uuid.uuid4()
    data = TaskCreate(title="任务A", requirements="描述")

    task = await task_service.create_task(fake_db, data, creator_id)

    assert task.title == "任务A"
    assert task.created_by == creator_id
    assert fake_db.commits == 1
    assert fake_db.refreshes == 1


@pytest.mark.asyncio
async def test_get_task(fake_db):
    task = Task(title="任务X", created_by=uuid.uuid4())
    fake_db.execute_result = FakeExecuteResult(scalar_value=task)

    result = await task_service.get_task(fake_db, uuid.uuid4())

    assert result is task


@pytest.mark.asyncio
async def test_delete_task_commits(fake_db):
    await task_service.delete_task(fake_db, uuid.uuid4())
    assert fake_db.commits == 1
