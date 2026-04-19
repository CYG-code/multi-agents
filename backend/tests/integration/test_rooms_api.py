import uuid

from app.models.room import Room, RoomStatus


def test_list_rooms(client, monkeypatch):
    room = Room(
        id=uuid.uuid4(),
        name="讨论室A",
        created_by=uuid.uuid4(),
        status=RoomStatus.waiting,
    )

    async def _mock_get_rooms(_db, _status=None):
        return [room]

    async def _mock_member_count(_db, _room_id):
        return 3

    monkeypatch.setattr("app.routers.rooms.room_service.get_rooms", _mock_get_rooms)
    monkeypatch.setattr("app.routers.rooms.room_service.get_member_count", _mock_member_count)

    resp = client.get("/api/rooms")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "讨论室A"
    assert data[0]["member_count"] == 3


def test_create_room(client, monkeypatch):
    room = Room(
        id=uuid.uuid4(),
        name="新房间",
        created_by=uuid.uuid4(),
        status=RoomStatus.waiting,
    )

    async def _mock_create_room(_db, data, _user_id):
        room.name = data.name
        return room

    monkeypatch.setattr("app.routers.rooms.room_service.create_room", _mock_create_room)

    resp = client.post("/api/rooms", json={"name": "新房间"})

    assert resp.status_code == 201
    assert resp.json()["name"] == "新房间"


def test_delete_room_requires_confirm_name(client, monkeypatch):
    room_id = uuid.uuid4()
    room = Room(
        id=room_id,
        name="确认房间",
        created_by=uuid.uuid4(),
        status=RoomStatus.waiting,
    )

    async def _mock_get_room(_db, _room_id):
        return room

    async def _mock_delete_room(_db, _room_id):
        return None

    monkeypatch.setattr("app.routers.rooms.room_service.get_room", _mock_get_room)
    monkeypatch.setattr("app.routers.rooms.room_service.delete_room", _mock_delete_room)

    resp = client.request("DELETE", f"/api/rooms/{room_id}", json={"confirm_name": "错误房间名"})

    assert resp.status_code == 400
    assert "不匹配" in resp.json()["detail"]


def test_delete_room_success(client, monkeypatch):
    room_id = uuid.uuid4()
    room = Room(
        id=room_id,
        name="确认房间",
        created_by=uuid.uuid4(),
        status=RoomStatus.waiting,
    )
    deleted = {"called": False}

    async def _mock_get_room(_db, _room_id):
        return room

    async def _mock_delete_room(_db, _room_id):
        deleted["called"] = True

    monkeypatch.setattr("app.routers.rooms.room_service.get_room", _mock_get_room)
    monkeypatch.setattr("app.routers.rooms.room_service.delete_room", _mock_delete_room)
    monkeypatch.setattr("app.routers.rooms.get_redis_client", lambda: (_ for _ in ()).throw(RuntimeError("no redis")))

    resp = client.request("DELETE", f"/api/rooms/{room_id}", json={"confirm_name": "确认房间"})

    assert resp.status_code == 200
    assert deleted["called"] is True
