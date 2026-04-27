import uuid

from app.models.task import Task


def test_list_tasks(client, monkeypatch):
    t = Task(id=uuid.uuid4(), title="Task A", created_by=uuid.uuid4())

    async def _mock_list_tasks(_db):
        return [t]

    monkeypatch.setattr("app.routers.tasks.task_service.list_tasks", _mock_list_tasks)

    resp = client.get("/api/tasks")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "Task A"


def test_get_task_404(client, monkeypatch):
    async def _mock_get_task(_db, _task_id):
        return None

    monkeypatch.setattr("app.routers.tasks.task_service.get_task", _mock_get_task)

    resp = client.get(f"/api/tasks/{uuid.uuid4()}")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Task not found"


def test_delete_task_success(client, fake_db, monkeypatch):
    task = Task(id=uuid.uuid4(), title="Task A", created_by=uuid.uuid4())
    deleted = {}

    async def _mock_get_task(_db, _task_id):
        return task

    async def _mock_delete_task(_db, task_id):
        deleted["task_id"] = task_id

    # no active room is using this task
    fake_db.execute_result = type("R", (), {"scalar_one_or_none": lambda self: None})()

    monkeypatch.setattr("app.routers.tasks.task_service.get_task", _mock_get_task)
    monkeypatch.setattr("app.routers.tasks.task_service.delete_task", _mock_delete_task)

    resp = client.delete(f"/api/tasks/{task.id}")

    assert resp.status_code == 200
    assert resp.json()["detail"] == "Task deleted"
    assert deleted["task_id"] == task.id


def test_delete_task_conflict_when_used_by_active_room(client, fake_db, monkeypatch):
    task = Task(id=uuid.uuid4(), title="Task A", created_by=uuid.uuid4())

    async def _mock_get_task(_db, _task_id):
        return task

    # active room exists
    fake_db.execute_result = type("R", (), {"scalar_one_or_none": lambda self: object()})()

    monkeypatch.setattr("app.routers.tasks.task_service.get_task", _mock_get_task)

    resp = client.delete(f"/api/tasks/{task.id}")

    assert resp.status_code == 409
    assert resp.json()["detail"] == "Task is used by an active room"
