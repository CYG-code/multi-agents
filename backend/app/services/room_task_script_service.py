"""
Room-scoped task script service.

Provides helpers to read/write per-room task script state without
affecting the existing task_script_service (which stores state on
Task.scripts). This is the foundation for migrating the task-flow
state from shared Task level to room-isolated level.

This service is NOT yet wired into the main propose/acquire/confirm
flow. It only provides data access helpers.
"""

from __future__ import annotations

import copy
import json

from fastapi import HTTPException
from sqlalchemy import select

from app.db.session import Base  # noqa: F401
from app.models.room import Room
from app.models.room_task_script import RoomTaskScript
from app.models.task import Task
from app.services import task_service


def normalize_room_task_scripts(raw_scripts) -> dict:
    """
    Normalize a raw scripts value into the canonical shape.

    Mirrors the logic in task_script_service._normalize_scripts but
    exposed for use by room-scoped operations.
    """
    if isinstance(raw_scripts, dict):
        history = raw_scripts.get("history")
        pending = raw_scripts.get("pending_proposal")
        return {
            "current_status": _to_text(raw_scripts.get("current_status")),
            "next_goal": _to_text(raw_scripts.get("next_goal")),
            "history": history if isinstance(history, list) else [],
            "pending_proposal": pending if isinstance(pending, dict) else None,
        }

    if isinstance(raw_scripts, str):
        return {
            "current_status": raw_scripts.strip(),
            "next_goal": "",
            "history": [],
            "pending_proposal": None,
        }

    return {
        "current_status": "",
        "next_goal": "",
        "history": [],
        "pending_proposal": None,
    }


def _to_text(value) -> str:
    """Same helper as in task_script_service."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    try:
        return json.dumps(value, ensure_ascii=False).strip()
    except Exception:
        return str(value).strip()


def _default_scripts() -> dict:
    return {
        "current_status": "",
        "next_goal": "",
        "history": [],
        "pending_proposal": None,
    }


async def get_or_create_room_task_script(
    db,
    room: Room,
) -> RoomTaskScript:
    """
    Get the RoomTaskScript for the given room, creating one if it does
    not exist.

    On creation, the initial scripts are derived from the room's bound
    task.scripts (a deep-copied snapshot, NOT a shared reference), with
    pending_proposal cleared to prevent stale task-level state leaking
    into the room.

    If the room has no bound task, or the task has no scripts, a default
    empty structure is used.

    Returns the RoomTaskScript record.
    """
    result = await db.execute(
        select(RoomTaskScript).where(RoomTaskScript.room_id == room.id)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    # Derive initial scripts from the bound task (if any)
    initial_scripts: dict = _default_scripts()
    if room.task_id is not None:
        task = await task_service.get_task(db, room.task_id)
        if task is not None and task.scripts is not None:
            parsed = normalize_room_task_scripts(task.scripts)
            # Deep copy so the room gets its own independent state
            initial_scripts = copy.deepcopy(parsed)

    # Always clear pending_proposal — pending state must never
    # propagate from task template into room.
    initial_scripts["pending_proposal"] = None

    record = RoomTaskScript(
        room_id=room.id,
        task_id=room.task_id,
        scripts=initial_scripts,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def update_room_task_script(
    db,
    room: Room,
    scripts: dict,
) -> RoomTaskScript:
    """Update the scripts for an existing RoomTaskScript record."""
    record = await get_or_create_room_task_script(db, room)
    record.scripts = scripts
    await db.commit()
    await db.refresh(record)
    return record
