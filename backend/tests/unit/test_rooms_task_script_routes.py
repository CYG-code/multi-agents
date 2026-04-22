import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.room import Room
from app.models.user import User, UserRole
from app.routers import rooms
from tests.conftest import FakeDBSession, FakeExecuteResult


def _student_user() -> User:
    return User(
        id=uuid.uuid4(),
        username="student_1",
        password_hash="x",
        display_name="Student 1",
        role=UserRole.student,
    )


def _teacher_user() -> User:
    return User(
        id=uuid.uuid4(),
        username="teacher_1",
        password_hash="x",
        display_name="Teacher 1",
        role=UserRole.teacher,
    )


def _build_client(fake_db: FakeDBSession, user: User) -> TestClient:
    app = FastAPI()
    app.include_router(rooms.router, prefix="/api/rooms", tags=["rooms"])

    async def override_get_db():
        yield fake_db

    async def override_get_current_user():
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    return TestClient(app)


def test_get_task_script_endpoint_returns_state(fake_db, monkeypatch):
    room_id = uuid.uuid4()
    task_id = uuid.uuid4()
    room = Room(id=room_id, name="R1", created_by=uuid.uuid4())
    room.task_id = task_id
    fake_db.execute_result = FakeExecuteResult(scalar_value=object())
    client = _build_client(fake_db, _student_user())

    async def _fake_get_room(_db, _room_id):
        return room

    async def _fake_get_task(_db, _task_id):
        return object()

    def _fake_state(_task):
        return {"task_id": str(task_id), "current_status": "S", "next_goal": "G", "history": [], "pending_proposal": None}

    monkeypatch.setattr(rooms.room_service, "get_room", _fake_get_room)
    monkeypatch.setattr(rooms.task_service, "get_task", _fake_get_task)
    monkeypatch.setattr(rooms.task_script_service, "get_task_script_state", _fake_state)

    resp = client.get(f"/api/rooms/{room_id}/task-script")

    assert resp.status_code == 200
    assert resp.json()["next_goal"] == "G"


def test_confirm_task_script_forbidden_for_teacher(fake_db, monkeypatch):
    room_id = uuid.uuid4()
    room = Room(id=room_id, name="R1", created_by=uuid.uuid4())
    fake_db.execute_result = FakeExecuteResult(scalar_value=object())
    client = _build_client(fake_db, _teacher_user())

    async def _fake_get_room(_db, _room_id):
        return room

    monkeypatch.setattr(rooms.room_service, "get_room", _fake_get_room)

    resp = client.post(
        f"/api/rooms/{room_id}/task-script/confirm",
        json={"current_status": "S", "next_goal": "G"},
    )

    assert resp.status_code == 403
    assert "仅学生可确认" in resp.json()["detail"]


def test_confirm_task_script_calls_service_for_student(fake_db, monkeypatch):
    room_id = uuid.uuid4()
    room = Room(id=room_id, name="R1", created_by=uuid.uuid4())
    fake_db.execute_result = FakeExecuteResult(scalar_value=object())
    student = _student_user()
    client = _build_client(fake_db, student)
    called = {}

    async def _fake_get_room(_db, _room_id):
        return room

    async def _fake_confirm(_db, _room, _user, overrides=None):
        called["room"] = _room
        called["user"] = _user
        called["overrides"] = overrides
        return {"task_id": "t1", "current_status": "S2", "next_goal": "G2", "history": [], "pending_proposal": None}

    monkeypatch.setattr(rooms.room_service, "get_room", _fake_get_room)
    monkeypatch.setattr(rooms.task_script_service, "confirm_pending_proposal", _fake_confirm)

    resp = client.post(
        f"/api/rooms/{room_id}/task-script/confirm",
        json={"current_status": "S-Edited", "next_goal": "G-Edited", "student_feedback": "先小范围试跑"},
    )

    assert resp.status_code == 200
    assert resp.json()["current_status"] == "S2"
    assert called["room"] is room
    assert called["user"].id == student.id
    assert called["overrides"]["current_status"] == "S-Edited"
    assert called["overrides"]["student_feedback"] == "先小范围试跑"
