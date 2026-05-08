from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.room import Room

AGENT_MODE_NONE = "none"
AGENT_MODE_SINGLE = "single"
AGENT_MODE_MULTI = "multi"

ALLOWED_AGENT_MODES = {AGENT_MODE_NONE, AGENT_MODE_SINGLE, AGENT_MODE_MULTI}
MULTI_AGENT_ROLES = {
    "facilitator",
    "devil_advocate",
    "summarizer",
    "resource_finder",
    "encourager",
    "concept_explainer",
}
SINGLE_AGENT_ROLES = {"socratic"}


def normalize_agent_mode(value: str | None) -> str:
    if value is None:
        return AGENT_MODE_MULTI
    mode = str(value).strip().lower()
    if mode in ALLOWED_AGENT_MODES:
        return mode
    return AGENT_MODE_NONE


def is_multi_agent_role(agent_role: str) -> bool:
    return str(agent_role or "").strip().lower() in MULTI_AGENT_ROLES


def can_use_agent_role(agent_mode: str, agent_role: str) -> bool:
    mode = normalize_agent_mode(agent_mode)
    role = str(agent_role or "").strip().lower()
    if not role:
        return False
    if mode == AGENT_MODE_NONE:
        return False
    if mode == AGENT_MODE_SINGLE:
        return role in SINGLE_AGENT_ROLES
    # multi
    return role in MULTI_AGENT_ROLES


def should_run_auto_dispatcher(agent_mode: str) -> bool:
    return normalize_agent_mode(agent_mode) == AGENT_MODE_MULTI


async def get_room_agent_mode(room_id: str) -> str:
    try:
        parsed_room_id = UUID(str(room_id))
    except (TypeError, ValueError):
        return AGENT_MODE_NONE

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Room.agent_mode).where(Room.id == parsed_room_id))
            mode = result.scalar_one_or_none()
    except Exception:
        # If DB is unavailable during runtime checks, fail safe to disable agents.
        return AGENT_MODE_NONE

    if mode is None:
        return AGENT_MODE_NONE
    return normalize_agent_mode(str(mode))
