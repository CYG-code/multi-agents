from __future__ import annotations

import json
from datetime import datetime, timezone

from app.db.redis_client import get_redis_client

SAVED_HISTORY_MAX_LEN = 3


def _state_key(room_id: str) -> str:
    return f"room:{room_id}:writing_doc_state"


def _version_key(room_id: str) -> str:
    return f"room:{room_id}:writing_doc_version"


def _history_key(room_id: str) -> str:
    return f"room:{room_id}:writing_doc_history"


def _empty_state() -> dict:
    return {
        "content": "",
        "version": 0,
        "updated_at": None,
        "updated_by": None,
        "updated_by_display_name": None,
    }


async def get_writing_doc_state(room_id: str) -> dict:
    redis_client = get_redis_client()
    raw = await redis_client.get(_state_key(room_id))
    if not raw:
        return _empty_state()
    try:
        parsed = json.loads(raw)
    except Exception:
        return _empty_state()
    if not isinstance(parsed, dict):
        return _empty_state()
    return {
        "content": str(parsed.get("content") or ""),
        "version": int(parsed.get("version") or 0),
        "updated_at": parsed.get("updated_at"),
        "updated_by": parsed.get("updated_by"),
        "updated_by_display_name": parsed.get("updated_by_display_name"),
    }


async def _append_history(room_id: str, state: dict) -> None:
    redis_client = get_redis_client()
    await redis_client.lpush(_history_key(room_id), json.dumps(state, ensure_ascii=False))
    await redis_client.ltrim(_history_key(room_id), 0, SAVED_HISTORY_MAX_LEN - 1)


async def get_writing_doc_history(room_id: str, limit: int = 20) -> list[dict]:
    redis_client = get_redis_client()
    raw_items = await redis_client.lrange(_history_key(room_id), 0, max(0, limit - 1))
    results: list[dict] = []
    for raw in raw_items:
        try:
            parsed = json.loads(raw)
        except Exception:
            continue
        if not isinstance(parsed, dict):
            continue
        results.append(
            {
                "content": str(parsed.get("content") or ""),
                "version": int(parsed.get("version") or 0),
                "updated_at": parsed.get("updated_at"),
                "updated_by": parsed.get("updated_by"),
                "updated_by_display_name": parsed.get("updated_by_display_name"),
                "saved_at": parsed.get("saved_at"),
                "saved_by": parsed.get("saved_by"),
                "saved_by_display_name": parsed.get("saved_by_display_name"),
            }
        )
    return results


async def apply_writing_doc_update(
    room_id: str,
    content: str,
    updated_by: str,
    updated_by_display_name: str | None = None,
) -> dict:
    redis_client = get_redis_client()
    version = int(await redis_client.incr(_version_key(room_id)))
    state = {
        "content": str(content or ""),
        "version": version,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": str(updated_by),
        "updated_by_display_name": (updated_by_display_name or None),
    }
    await redis_client.set(_state_key(room_id), json.dumps(state, ensure_ascii=False))
    return state


async def apply_writing_doc_update_with_base_version(
    room_id: str,
    content: str,
    updated_by: str,
    updated_by_display_name: str | None = None,
    base_version: int | None = None,
) -> tuple[dict, bool]:
    """
    Returns (state, applied):
      - applied=True: update accepted and persisted
      - applied=False: client is stale; return current authoritative state
    """
    current_state = await get_writing_doc_state(room_id)
    current_version = int(current_state.get("version") or 0)
    if base_version is not None and int(base_version) < current_version:
        return current_state, False

    next_state = await apply_writing_doc_update(
        room_id,
        content,
        updated_by,
        updated_by_display_name=updated_by_display_name,
    )
    return next_state, True


async def restore_writing_doc_version(
    room_id: str,
    target_version: int,
    updated_by: str,
    updated_by_display_name: str | None = None,
) -> dict:
    history = await get_writing_doc_history(room_id, limit=SAVED_HISTORY_MAX_LEN)
    target = next((item for item in history if int(item.get("version") or 0) == int(target_version)), None)
    if not target:
        raise ValueError("target version not found")

    return await apply_writing_doc_update(
        room_id,
        target.get("content") or "",
        updated_by=updated_by,
        updated_by_display_name=updated_by_display_name,
    )


async def save_writing_doc_version(
    room_id: str,
    saved_by: str,
    saved_by_display_name: str | None = None,
) -> dict:
    state = await get_writing_doc_state(room_id)
    if int(state.get("version") or 0) <= 0:
        raise ValueError("writing doc is empty")

    snapshot = {
        "content": state.get("content") or "",
        "version": int(state.get("version") or 0),
        "updated_at": state.get("updated_at"),
        "updated_by": state.get("updated_by"),
        "updated_by_display_name": state.get("updated_by_display_name"),
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "saved_by": str(saved_by),
        "saved_by_display_name": saved_by_display_name or None,
    }
    await _append_history(room_id, snapshot)
    return snapshot
