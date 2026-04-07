import uuid

from app.models.task import Task


def test_list_tasks(client, monkeypatch):
    t = Task(id=uuid.uuid4(), title="任务A", created_by=uuid.uuid4())

    async def _mock_list_tasks(_db):
        return [t]

    monkeypatch.setattr("app.routers.tasks.task_service.list_tasks", _mock_list_tasks)

    resp = client.get("/api/tasks")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "任务A"


def test_get_task_404(client, monkeypatch):
    async def _mock_get_task(_db, _task_id):
        return None

    monkeypatch.setattr("app.routers.tasks.task_service.get_task", _mock_get_task)

    resp = client.get(f"/api/tasks/{uuid.uuid4()}")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "任务不存在"

