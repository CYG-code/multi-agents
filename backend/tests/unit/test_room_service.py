import uuid

import pytest

from app.models.room import Room, RoomStatus
from app.schemas.room import RoomCreate
from app.services import room_service
from tests.conftest import FakeExecuteResult


@pytest.mark.asyncio
async def test_create_room_persists_and_returns(fake_db):
    owner_id = uuid.uuid4()
    data = RoomCreate(name="讨论室A")

    room = await room_service.create_room(fake_db, data, owner_id)

    assert room.name == "讨论室A"
    assert room.created_by == owner_id
    assert fake_db.commits == 1
    assert fake_db.refreshes == 1


@pytest.mark.asyncio
async def test_update_room_status(fake_db):
    room = Room(name="讨论室B", created_by=uuid.uuid4(), status=RoomStatus.waiting)

    updated = await room_service.update_room_status(fake_db, room, RoomStatus.active)

    assert updated.status == RoomStatus.active
    assert fake_db.commits == 1
    assert fake_db.refreshes == 1


@pytest.mark.asyncio
async def test_get_room_returns_result_from_db(fake_db):
    room = Room(name="讨论室C", created_by=uuid.uuid4(), status=RoomStatus.waiting)
    fake_db.execute_result = FakeExecuteResult(scalar_value=room)

    found = await room_service.get_room(fake_db, uuid.uuid4())

    assert found is room


@pytest.mark.asyncio
async def test_delete_room_commits(fake_db):
    await room_service.delete_room(fake_db, uuid.uuid4())
    assert fake_db.commits == 1
