import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.user import User, UserRole
from app.routers import agents


class _FakeRedis:
    def __init__(self, data: dict[str, dict[str, str]] | None = None):
        self.data = data or {}

    async def hgetall(self, key: str):
        return self.data.get(key, {})


def _build_client_with_user(fake_db, user: User) -> TestClient:
    app = FastAPI()
    app.include_router(agents.router, prefix="/api/agents", tags=["agents"])

    async def override_get_db():
        yield fake_db

    async def override_get_current_user():
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    return TestClient(app)


def _task_payload(task_id: str, room_id: str | None) -> dict[str, dict[str, str]]:
    return {
        f"agent:task:{task_id}": {
            "task_id": task_id,
            "room_id": room_id or "",
            "agent_role": "facilitator",
            "trigger_type": "mention",
            "status": "queued",
            "reason": "test",
            "source_message_id": "msg-1",
            "created_at": "2026-01-01T00:00:00Z",
            "queued_at": "2026-01-01T00:00:01Z",
            "running_at": "",
            "finished_at": "",
            "error": "",
            "drop_reason": "",
        }
    }


def test_get_agent_task_status_returns_task(client, fake_db, monkeypatch):
    room_id = str(uuid.uuid4())
    task_id = "task-123"
    fake_db.execute_result = type("R", (), {"scalar_one_or_none": lambda self: object()})()

    redis_payload = {
        f"agent:task:{task_id}": {
            "task_id": task_id,
            "room_id": room_id,
            "agent_role": "facilitator",
            "trigger_type": "mention",
            "status": "queued",
            "reason": "test",
            "source_message_id": "msg-1",
            "created_at": "2026-01-01T00:00:00Z",
            "queued_at": "2026-01-01T00:00:01Z",
            "running_at": "",
            "finished_at": "",
            "error": "",
            "drop_reason": "",
        }
    }
    monkeypatch.setattr("app.routers.agents.get_redis_client", lambda: _FakeRedis(redis_payload))

    resp = client.get(f"/api/agents/tasks/{task_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == task_id
    assert data["room_id"] == room_id
    assert data["status"] == "queued"


def test_get_agent_task_status_404_when_missing(client, monkeypatch):
    monkeypatch.setattr("app.routers.agents.get_redis_client", lambda: _FakeRedis({}))

    resp = client.get("/api/agents/tasks/not-found")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Agent task not found"


def test_get_agent_task_status_requires_login(fake_db):
    app = FastAPI()
    app.include_router(agents.router, prefix="/api/agents", tags=["agents"])

    async def override_get_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)

    resp = test_client.get("/api/agents/tasks/task-1")
    assert resp.status_code == 401


def test_teacher_can_view_any_room_task(fake_db, monkeypatch):
    task_id = "task-teacher-ok"
    room_id = str(uuid.uuid4())
    teacher = User(
        id=uuid.uuid4(),
        username="teacher_diag",
        password_hash="x",
        display_name="Teacher Diag",
        role=UserRole.teacher,
    )
    test_client = _build_client_with_user(fake_db, teacher)
    monkeypatch.setattr("app.routers.agents.get_redis_client", lambda: _FakeRedis(_task_payload(task_id, room_id)))

    resp = test_client.get(f"/api/agents/tasks/{task_id}")
    assert resp.status_code == 200
    assert resp.json()["room_id"] == room_id


def test_student_room_member_can_view_own_room_task(fake_db, monkeypatch):
    task_id = "task-member-ok"
    room_id = str(uuid.uuid4())
    student = User(
        id=uuid.uuid4(),
        username="student_member",
        password_hash="x",
        display_name="Student Member",
        role=UserRole.student,
    )
    test_client = _build_client_with_user(fake_db, student)
    fake_db.execute_result = type("R", (), {"scalar_one_or_none": lambda self: object()})()
    monkeypatch.setattr("app.routers.agents.get_redis_client", lambda: _FakeRedis(_task_payload(task_id, room_id)))

    resp = test_client.get(f"/api/agents/tasks/{task_id}")
    assert resp.status_code == 200
    assert resp.json()["task_id"] == task_id


def test_student_non_member_cannot_view_other_room_task(fake_db, monkeypatch):
    task_id = "task-non-member-deny"
    room_id = str(uuid.uuid4())
    student = User(
        id=uuid.uuid4(),
        username="student_non_member",
        password_hash="x",
        display_name="Student Non Member",
        role=UserRole.student,
    )
    test_client = _build_client_with_user(fake_db, student)
    fake_db.execute_result = type("R", (), {"scalar_one_or_none": lambda self: None})()
    monkeypatch.setattr("app.routers.agents.get_redis_client", lambda: _FakeRedis(_task_payload(task_id, room_id)))

    resp = test_client.get(f"/api/agents/tasks/{task_id}")
    assert resp.status_code == 403


def test_student_task_without_room_id_returns_403_current_behavior(fake_db, monkeypatch):
    task_id = "task-no-room-student"
    student = User(
        id=uuid.uuid4(),
        username="student_no_room",
        password_hash="x",
        display_name="Student No Room",
        role=UserRole.student,
    )
    test_client = _build_client_with_user(fake_db, student)
    monkeypatch.setattr("app.routers.agents.get_redis_client", lambda: _FakeRedis(_task_payload(task_id, None)))

    resp = test_client.get(f"/api/agents/tasks/{task_id}")
    assert resp.status_code == 403
