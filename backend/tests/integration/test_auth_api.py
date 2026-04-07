import uuid

from app.models.user import User, UserRole
from app.services.auth_service import hash_password
from tests.conftest import FakeExecuteResult


def test_login_success(client, fake_db):
    user = User(
        id=uuid.uuid4(),
        username="alice",
        password_hash=hash_password("password123"),
        display_name="Alice",
        role=UserRole.student,
    )
    fake_db.execute_result = FakeExecuteResult(scalar_value=user)

    resp = client.post("/api/auth/login", json={"username": "alice", "password": "password123"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["access_token"]
    assert data["user"]["username"] == "alice"


def test_login_invalid_credentials(client, fake_db):
    fake_db.execute_result = FakeExecuteResult(scalar_value=None)

    resp = client.post("/api/auth/login", json={"username": "not-exist", "password": "x"})

    assert resp.status_code == 401
    assert resp.json()["detail"] == "用户名或密码错误"

