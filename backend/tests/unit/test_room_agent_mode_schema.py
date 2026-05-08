from pathlib import Path

import pytest
from pydantic import ValidationError

from app.models.room import Room
from app.schemas.room import RoomCreate, RoomResponse


EXPECTED_AGENT_MODES = {"none", "single", "multi"}
EXPECTED_DEFAULT_AGENT_MODE = "multi"


def _make_valid_room_create_payload(**overrides):
    payload = {"name": "Room A"}
    payload.update(overrides)
    return payload


def test_room_create_accepts_valid_agent_modes():
    for mode in EXPECTED_AGENT_MODES:
        model = RoomCreate(**_make_valid_room_create_payload(agent_mode=mode))
        assert "agent_mode" in model.model_fields_set
        assert getattr(model, "agent_mode") == mode


def test_room_create_defaults_agent_mode_to_multi():
    model = RoomCreate(**_make_valid_room_create_payload())
    assert hasattr(model, "agent_mode")
    assert getattr(model, "agent_mode") == EXPECTED_DEFAULT_AGENT_MODE


@pytest.mark.parametrize("invalid_mode", ["no_agent", "multi_agent", "socratic", "", "invalid_mode"])
def test_room_create_rejects_invalid_agent_mode(invalid_mode: str):
    with pytest.raises(ValidationError):
        RoomCreate(**_make_valid_room_create_payload(agent_mode=invalid_mode))


def test_room_response_includes_agent_mode():
    field_names = set(RoomResponse.model_fields.keys())
    assert "agent_mode" in field_names



def test_room_model_declares_agent_mode_column():
    column_names = set(Room.__table__.columns.keys())
    assert "agent_mode" in column_names


def test_existing_agent_mode_migration_matches_expected_values():
    migration_path = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "9a2d1f7c4b11_add_room_agent_mode.py"
    assert migration_path.exists(), "Expected migration file is missing"

    content = migration_path.read_text(encoding="utf-8")
    assert "agent_mode" in content

    # The migration should reflect the current experiment-mode design.
    assert "none" in content
    assert "single" in content
    assert "multi" in content
