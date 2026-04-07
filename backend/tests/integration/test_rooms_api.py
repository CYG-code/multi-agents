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

