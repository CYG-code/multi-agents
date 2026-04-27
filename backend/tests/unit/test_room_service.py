import uuid
from datetime import datetime, timezone

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


@pytest.mark.asyncio
async def test_start_room_timer_sets_timer_fields(fake_db):
    room = Room(name="timer", created_by=uuid.uuid4(), status=RoomStatus.waiting)

    updated = await room_service.start_room_timer(fake_db, room, duration_minutes=90)

    assert updated.timer_started_at is not None
    assert updated.timer_deadline_at is not None
    assert updated.timer_stopped_at is None
    delta = updated.timer_deadline_at - updated.timer_started_at
    assert int(delta.total_seconds()) == 90 * 60
    assert updated.timer_started_at.tzinfo == timezone.utc
    assert fake_db.commits == 1
    assert fake_db.refreshes == 1


@pytest.mark.asyncio
async def test_reset_room_timer_clears_timer_fields(fake_db):
    room = Room(name="timer", created_by=uuid.uuid4(), status=RoomStatus.waiting)
    room.timer_started_at = datetime.now(timezone.utc)
    room.timer_deadline_at = room.timer_started_at
    room.timer_stopped_at = room.timer_started_at

    updated = await room_service.reset_room_timer(fake_db, room)

    assert updated.timer_started_at is None
    assert updated.timer_deadline_at is None
    assert updated.timer_stopped_at is None
    assert fake_db.commits == 1
    assert fake_db.refreshes == 1
