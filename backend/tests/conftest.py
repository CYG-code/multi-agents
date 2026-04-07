from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.dependencies import get_current_user, require_teacher
from app.models.user import User, UserRole
from app.routers import auth, rooms, tasks


class FakeScalarResult:
    def __init__(self, value: Any):
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


class FakeScalars:
    def __init__(self, values: list[Any]):
        self._values = values

    def all(self) -> list[Any]:
        return list(self._values)


class FakeExecuteResult:
    def __init__(self, scalar_value: Any = None, scalar_list: list[Any] | None = None):
        self._scalar_value = scalar_value
        self._scalar_list = scalar_list or []

    def scalar_one_or_none(self) -> Any:
        return self._scalar_value

    def scalar_one(self) -> Any:
        return self._scalar_value

    def scalars(self) -> FakeScalars:
        return FakeScalars(self._scalar_list)

    def fetchall(self) -> list[Any]:
        return list(self._scalar_list)


class FakeDBSession:
    def __init__(self):
        self.execute_result = FakeExecuteResult()
        self.added: list[Any] = []
        self.commits = 0
        self.refreshes = 0

    async def execute(self, _stmt: Any) -> FakeExecuteResult:
        return self.execute_result

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.commits += 1

    async def refresh(self, _obj: Any) -> None:
        self.refreshes += 1


@pytest.fixture
def fake_db() -> FakeDBSession:
    return FakeDBSession()


@pytest.fixture
def current_user_student() -> User:
    return User(
        username="student_1",
        password_hash="x",
        display_name="Student 1",
        role=UserRole.student,
    )


@pytest.fixture
def current_user_teacher() -> User:
    return User(
        username="teacher_1",
        password_hash="x",
        display_name="Teacher 1",
        role=UserRole.teacher,
    )


@pytest.fixture
def test_app(
    fake_db: FakeDBSession,
    current_user_student: User,
    current_user_teacher: User,
) -> FastAPI:
    app = FastAPI()
    app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
    app.include_router(rooms.router, prefix="/api/rooms", tags=["房间"])
    app.include_router(tasks.router, prefix="/api/tasks", tags=["任务"])

    async def override_get_db() -> AsyncIterator[FakeDBSession]:
        yield fake_db

    async def override_get_current_user() -> User:
        return current_user_student

    async def override_require_teacher() -> User:
        return current_user_teacher

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[require_teacher] = override_require_teacher
    return app


@pytest.fixture
def client(test_app: FastAPI) -> TestClient:
    return TestClient(test_app)

