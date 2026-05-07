"""
Unit tests for room_task_script_service.

Tests the get_or_create_room_task_script helper that provides
room-isolated task script state. No LLM, no Redis, no Bailian calls.
"""

import uuid
import copy
import pytest

from app.models.room import Room
from app.models.room_task_script import RoomTaskScript
from app.models.task import Task
from app.models.user import User, UserRole
from app.services import room_task_script_service as rts


# ---------------------------------------------------------------------------
# Fixture helpers (lightweight; fake_db is provided by tests/conftest.py)
# ---------------------------------------------------------------------------


def _make_room(task_id: uuid.UUID | None = None) -> Room:
    room = Room(id=uuid.uuid4(), name="Test Room", created_by=uuid.uuid4())
    room.task_id = task_id
    return room


def _make_task(
    scripts: dict | str | None = None,
) -> Task:
    return Task(
        id=uuid.uuid4(),
        title="Test Task",
        created_by=uuid.uuid4(),
        scripts=scripts,
    )


def _make_user() -> User:
    return User(
        id=uuid.uuid4(),
        username="tester",
        password_hash="x",
        display_name="Tester",
        role=UserRole.student,
    )


# ---------------------------------------------------------------------------
# Tests: get_or_create_room_task_script
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_or_create_creates_new_record(fake_db, monkeypatch):
    """A room with no prior RoomTaskScript gets one created."""
    task = _make_task(scripts={"current_status": "S", "next_goal": "G", "history": [], "pending_proposal": None})
    room = _make_room(task_id=task.id)

    async def _fake_get_task(_db, _task_id):
        return task
    monkeypatch.setattr(rts.task_service, "get_task", _fake_get_task)

    record = await rts.get_or_create_room_task_script(fake_db, room)

    assert record is not None
    assert isinstance(record, RoomTaskScript)
    assert record.room_id == room.id
    assert record.task_id == task.id
    assert record.scripts is not None


@pytest.mark.asyncio
async def test_get_or_create_returns_existing_record(fake_db, monkeypatch):
    """Calling get_or_create a second time returns the same row."""
    task = _make_task()
    room = _make_room(task_id=task.id)

    async def _fake_get_task(_db, _task_id):
        return task
    monkeypatch.setattr(rts.task_service, "get_task", _fake_get_task)

    first = await rts.get_or_create_room_task_script(fake_db, room)
    second = await rts.get_or_create_room_task_script(fake_db, room)

    assert first.id == second.id
    assert first.room_id == second.room_id


@pytest.mark.asyncio
async def test_multiple_rooms_same_task_get_independent_records(fake_db, monkeypatch):
    """
    Three rooms binding the same task_id each get their own
    RoomTaskScript row with independent scripts.
    """
    task = _make_task(scripts={"current_status": "Start", "next_goal": "Go", "history": [], "pending_proposal": None})
    room_a = _make_room(task_id=task.id)
    room_b = _make_room(task_id=task.id)
    room_c = _make_room(task_id=task.id)

    async def _fake_get_task(_db, _task_id):
        return task
    monkeypatch.setattr(rts.task_service, "get_task", _fake_get_task)

    ra = await rts.get_or_create_room_task_script(fake_db, room_a)
    rb = await rts.get_or_create_room_task_script(fake_db, room_b)
    rc = await rts.get_or_create_room_task_script(fake_db, room_c)

    # Different RoomTaskScript objects for different rooms
    assert ra is not rb
    assert ra is not rc
    assert rb is not rc

    # Different room_ids
    assert ra.room_id == room_a.id
    assert rb.room_id == room_b.id
    assert rc.room_id == room_c.id

    # All have the same task_id
    assert ra.task_id == task.id
    assert rb.task_id == task.id
    assert rc.task_id == task.id


@pytest.mark.asyncio
async def test_modifying_one_room_scripts_does_not_affect_others(fake_db, monkeypatch):
    """
    Room A modifies its scripts.pending_proposal; Room B and C must
    NOT see that change — proving true isolation.
    """
    task = _make_task(scripts={"current_status": "S", "next_goal": "G", "history": [], "pending_proposal": None})
    room_a = _make_room(task_id=task.id)
    room_b = _make_room(task_id=task.id)
    room_c = _make_room(task_id=task.id)

    async def _fake_get_task(_db, _task_id):
        return task
    monkeypatch.setattr(rts.task_service, "get_task", _fake_get_task)

    ra = await rts.get_or_create_room_task_script(fake_db, room_a)
    rb = await rts.get_or_create_room_task_script(fake_db, room_b)
    rc = await rts.get_or_create_room_task_script(fake_db, room_c)

    # Mutate Room A's scripts in place
    ra.scripts["pending_proposal"] = {
        "id": "prop-a",
        "agent_role": "facilitator",
        "current_status": "A did work",
        "next_goal": "A continues",
    }

    # Room B and C are distinct objects — their scripts are unaffected
    assert rb.scripts["pending_proposal"] is None, \
        "Room B must NOT see Room A's pending_proposal"
    assert rc.scripts["pending_proposal"] is None, \
        "Room C must NOT see Room A's pending_proposal"

    # Room A still has it
    assert ra.scripts["pending_proposal"] is not None
    assert ra.scripts["pending_proposal"]["id"] == "prop-a"


@pytest.mark.asyncio
async def test_initial_scripts_copied_from_task_scripts(fake_db, monkeypatch):
    """
    On creation, scripts are populated from the bound task's scripts
    (deep copy, not shared reference).
    """
    task_scripts = {
        "current_status": "Task status",
        "next_goal": "Task goal",
        "history": [{"id": "h1", "action": "init"}],
        "pending_proposal": None,
    }
    task = _make_task(scripts=task_scripts)
    room = _make_room(task_id=task.id)

    async def _fake_get_task(_db, _task_id):
        return task
    monkeypatch.setattr(rts.task_service, "get_task", _fake_get_task)

    record = await rts.get_or_create_room_task_script(fake_db, room)

    assert record.scripts["current_status"] == "Task status"
    assert record.scripts["next_goal"] == "Task goal"
    assert len(record.scripts["history"]) == 1
    assert record.scripts["history"][0]["id"] == "h1"
    # pending_proposal must be None even if task had one
    assert record.scripts["pending_proposal"] is None


@pytest.mark.asyncio
async def test_initial_scripts_pending_proposal_cleared(fake_db, monkeypatch):
    """
    Even if the Task.scripts has a pending_proposal, the room-level
    copy must clear it — pending state must never leak from template.
    """
    task_scripts = {
        "current_status": "S",
        "next_goal": "G",
        "history": [],
        "pending_proposal": {
            "id": "stale-proposal",
            "agent_role": "facilitator",
            "current_status": "Stale",
            "next_goal": "Stale goal",
        },
    }
    task = _make_task(scripts=task_scripts)
    room = _make_room(task_id=task.id)

    async def _fake_get_task(_db, _task_id):
        return task
    monkeypatch.setattr(rts.task_service, "get_task", _fake_get_task)

    record = await rts.get_or_create_room_task_script(fake_db, room)

    assert record.scripts["pending_proposal"] is None, \
        "pending_proposal must be cleared on room-level copy"


@pytest.mark.asyncio
async def test_initial_scripts_deep_copy_isolation(fake_db, monkeypatch):
    """
    The room's scripts are a deep copy, not a reference. Mutating the
    original task.scripts must NOT affect the room's copy, and vice
    versa.
    """
    task_scripts = {
        "current_status": "Original",
        "next_goal": "Original goal",
        "history": [{"id": "h1"}],
        "pending_proposal": None,
    }
    task = _make_task(scripts=task_scripts)
    room = _make_room(task_id=task.id)

    async def _fake_get_task(_db, _task_id):
        return task
    monkeypatch.setattr(rts.task_service, "get_task", _fake_get_task)

    record = await rts.get_or_create_room_task_script(fake_db, room)

    # Mutate original task scripts
    task.scripts["current_status"] = "Mutated"
    task.scripts["history"].append({"id": "h2"})

    # Room copy must remain unchanged
    assert record.scripts["current_status"] == "Original"
    assert len(record.scripts["history"]) == 1
    assert record.scripts["history"][0]["id"] == "h1"

    # Mutate room copy
    record.scripts["current_status"] = "Room mutates"
    # Task original must NOT see this
    assert task.scripts["current_status"] == "Mutated"


@pytest.mark.asyncio
async def test_no_task_id_gets_default_scripts(fake_db, monkeypatch):
    """A room with no bound task gets the default empty scripts."""
    room = _make_room(task_id=None)

    record = await rts.get_or_create_room_task_script(fake_db, room)

    assert record.scripts["current_status"] == ""
    assert record.scripts["next_goal"] == ""
    assert record.scripts["history"] == []
    assert record.scripts["pending_proposal"] is None
    assert record.task_id is None


@pytest.mark.asyncio
async def test_task_with_null_scripts_gets_default(fake_db, monkeypatch):
    """A task whose scripts column is None gets defaults."""
    task = _make_task(scripts=None)
    room = _make_room(task_id=task.id)

    async def _fake_get_task(_db, _task_id):
        return task
    monkeypatch.setattr(rts.task_service, "get_task", _fake_get_task)

    record = await rts.get_or_create_room_task_script(fake_db, room)

    assert record.scripts["current_status"] == ""
    assert record.scripts["next_goal"] == ""
    assert record.scripts["history"] == []
    assert record.scripts["pending_proposal"] is None


# ---------------------------------------------------------------------------
# Tests: normalize_room_task_scripts
# ---------------------------------------------------------------------------


class TestNormalizeRoomTaskScripts:
    def test_dict_input(self):
        raw = {"current_status": "S", "next_goal": "G", "history": [{"id": "h1"}], "pending_proposal": None}
        result = rts.normalize_room_task_scripts(raw)
        assert result["current_status"] == "S"
        assert result["next_goal"] == "G"
        assert result["history"] == [{"id": "h1"}]
        assert result["pending_proposal"] is None

    def test_dict_input_missing_keys(self):
        raw = {"current_status": "S"}
        result = rts.normalize_room_task_scripts(raw)
        assert result["current_status"] == "S"
        assert result["next_goal"] == ""
        assert result["history"] == []
        assert result["pending_proposal"] is None

    def test_string_input(self):
        result = rts.normalize_room_task_scripts("just a status string")
        assert result["current_status"] == "just a status string"
        assert result["next_goal"] == ""
        assert result["history"] == []
        assert result["pending_proposal"] is None

    def test_none_input(self):
        result = rts.normalize_room_task_scripts(None)
        assert result["current_status"] == ""
        assert result["next_goal"] == ""
        assert result["history"] == []
        assert result["pending_proposal"] is None

    def test_history_not_list_becomes_empty(self):
        raw = {"current_status": "S", "next_goal": "G", "history": "not-a-list"}
        result = rts.normalize_room_task_scripts(raw)
        assert result["history"] == []

    def test_dict_pending_proposal_preserved(self):
        raw = {"current_status": "S", "next_goal": "G", "history": [], "pending_proposal": {"id": "p1"}}
        result = rts.normalize_room_task_scripts(raw)
        assert result["pending_proposal"] == {"id": "p1"}
