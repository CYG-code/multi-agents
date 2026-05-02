from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone

from app.db.redis_client import get_redis_client

QUEUE_KEY_PREFIX = "agent_queue"
TASK_STATUS_KEY_PREFIX = "agent:task"
TASK_STATUS_TTL_SECONDS = 24 * 60 * 60
MENTION_ENTRY_QUEUE_KEY = "agent:mention_entry_queue"
MENTION_ENTRY_KEY_PREFIX = "agent:mention_entry"
MENTION_ENTRY_STATUS_KEY_PREFIX = "agent:mention_entry_status"
MENTION_ENTRY_TTL_SECONDS = 24 * 60 * 60
AGENT_DEBUG_LOG = os.getenv("AGENT_DEBUG_LOG", "").lower() == "true"


def _agent_log(event: str, extra: dict | None = None) -> None:
    if not AGENT_DEBUG_LOG:
        return
    payload = {"event": event, "ts": datetime.now(timezone.utc).isoformat()}
    if extra:
        payload["extra"] = extra
    print("[AGENT-QUEUE-DEBUG]", payload, flush=True)


def queue_key(room_id: str) -> str:
    return f"{QUEUE_KEY_PREFIX}:{room_id}"


def task_status_key(task_id: str) -> str:
    return f"{TASK_STATUS_KEY_PREFIX}:{task_id}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def mention_entry_key(entry_id: str) -> str:
    return f"{MENTION_ENTRY_KEY_PREFIX}:{entry_id}"


def mention_entry_status_key(entry_id: str) -> str:
    return f"{MENTION_ENTRY_STATUS_KEY_PREFIX}:{entry_id}"


def _normalize_task(task: dict) -> dict:
    normalized = dict(task)
    normalized.setdefault("task_id", str(uuid.uuid4()))
    normalized.setdefault("priority", 5)
    normalized.setdefault("triggered_at", time.time())
    normalized.setdefault("room_id", "")
    normalized.setdefault("agent_role", "")
    normalized.setdefault("trigger_type", "manual")
    normalized.setdefault("target_dimension", "none")
    normalized.setdefault("reason", "System requests one collaboration support intervention.")
    normalized.setdefault("strategy", "Provide one concise and actionable help for the current discussion.")
    normalized.setdefault("evidence", [])
    normalized.setdefault("current_phase", "unknown")
    normalized.setdefault("source_message_id", None)
    normalized.setdefault("snapshot_id", None)
    normalized.setdefault("intervention_id", None)
    return normalized


def _validate_task(task: dict) -> None:
    required = [
        "room_id",
        "agent_role",
        "trigger_type",
        "reason",
        "strategy",
        "priority",
        "triggered_at",
    ]
    missing = [key for key in required if task.get(key) in (None, "")]
    if missing:
        raise ValueError(f"agent task missing required fields: {missing}")


async def enqueue_task(room_id: str, task: dict, delay_seconds: float = 0.0) -> dict:
    redis_client = get_redis_client()
    execute_at = time.time() + max(0.0, float(delay_seconds))
    normalized = _normalize_task(task)
    normalized["room_id"] = normalized.get("room_id") or room_id
    _validate_task(normalized)
    qkey = queue_key(room_id)
    _agent_log(
        "agent_enqueue_start",
        {
            "task_id": normalized.get("task_id"),
            "room_id": room_id,
            "agent_role": normalized.get("agent_role"),
            "trigger_type": normalized.get("trigger_type"),
            "source_message_id": normalized.get("source_message_id"),
            "queue_key": qkey,
            "priority": normalized.get("priority"),
            "created_at": normalized.get("triggered_at"),
            "execute_at": execute_at,
        },
    )
    task_json = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    await redis_client.zadd(qkey, {task_json: execute_at})
    await set_task_status(
        task_id=str(normalized.get("task_id")),
        room_id=room_id,
        agent_role=str(normalized.get("agent_role") or ""),
        trigger_type=str(normalized.get("trigger_type") or "manual"),
        status="queued",
        reason=str(normalized.get("reason") or ""),
        source_message_id=normalized.get("source_message_id"),
        queued_at=now_iso(),
        created_at=str(normalized.get("created_at") or normalized.get("triggered_at") or now_iso()),
    )
    qlen = int(await redis_client.zcard(qkey))
    _agent_log(
        "agent_enqueue_done",
        {
            "task_id": normalized.get("task_id"),
            "room_id": room_id,
            "queue_key": qkey,
            "queue_length": qlen,
        },
    )
    return normalized


async def dequeue_tasks(room_id: str) -> list[dict]:
    redis_client = get_redis_client()
    qkey = queue_key(room_id)
    now = time.time()
    raw_tasks = await redis_client.zrangebyscore(qkey, min=0, max=now)
    if not raw_tasks:
        _agent_log(
            "agent_worker_task_none",
            {"room_id": room_id, "queue_key": qkey, "queue_length": int(await redis_client.zcard(qkey))},
        )
        return []

    await redis_client.zrem(qkey, *raw_tasks)

    parsed: list[dict] = []
    for raw in raw_tasks:
        try:
            parsed.append(json.loads(raw))
        except Exception:
            continue

    parsed.sort(
        key=lambda t: (
            int(t.get("priority", 5)),
            float(t.get("triggered_at", 0)),
            str(t.get("task_id", "")),
        )
    )
    _agent_log(
        "agent_worker_task_popped",
        {
            "room_id": room_id,
            "queue_key": qkey,
            "popped_count": len(parsed),
            "remaining_queue_length": int(await redis_client.zcard(qkey)),
            "task_ids": [str(t.get("task_id")) for t in parsed],
        },
    )
    return parsed


async def requeue_task(room_id: str, task: dict, delay_seconds: float = 5.0) -> dict:
    return await enqueue_task(room_id, task, delay_seconds=delay_seconds)


async def set_task_status(
    *,
    task_id: str,
    room_id: str,
    agent_role: str,
    trigger_type: str,
    status: str,
    reason: str = "",
    source_message_id: str | None = None,
    running_at: str | None = None,
    finished_at: str | None = None,
    error: str | None = None,
    drop_reason: str | None = None,
    created_at: str | None = None,
    queued_at: str | None = None,
) -> None:
    if not task_id:
        return
    redis_client = get_redis_client()
    key = task_status_key(task_id)
    payload = {
        "task_id": task_id,
        "room_id": room_id,
        "agent_role": agent_role,
        "trigger_type": trigger_type,
        "status": status,
        "reason": reason or "",
        "source_message_id": source_message_id or "",
        "running_at": running_at or "",
        "finished_at": finished_at or "",
        "error": error or "",
        "drop_reason": drop_reason or "",
    }
    if created_at is not None:
        payload["created_at"] = created_at
    if queued_at is not None:
        payload["queued_at"] = queued_at
    await redis_client.hset(key, mapping=payload)
    await redis_client.expire(key, TASK_STATUS_TTL_SECONDS)


async def update_task_status_fields(task_id: str, **fields: str) -> None:
    if not task_id or not fields:
        return
    redis_client = get_redis_client()
    key = task_status_key(task_id)
    await redis_client.hset(key, mapping={k: str(v) for k, v in fields.items()})
    await redis_client.expire(key, TASK_STATUS_TTL_SECONDS)


async def get_task_status(task_id: str) -> dict[str, str]:
    if not task_id:
        return {}
    redis_client = get_redis_client()
    key = task_status_key(task_id)
    data = await redis_client.hgetall(key)
    return {str(k): str(v) for k, v in (data or {}).items()}


async def create_mention_entry(
    *,
    room_id: str,
    agent_role: str,
    source_message_id: str,
    student_name: str,
    reason: str,
    strategy: str,
    trigger_type: str = "mention",
    entry_id: str | None = None,
    created_at: float | None = None,
    expire_at: float | None = None,
) -> dict[str, str]:
    redis_client = get_redis_client()
    now_ts = float(created_at if created_at is not None else time.time())
    expiry_ts = float(expire_at if expire_at is not None else now_ts + MENTION_ENTRY_TTL_SECONDS)
    eid = str(entry_id or uuid.uuid4())
    entry = {
        "entry_id": eid,
        "room_id": room_id,
        "agent_role": agent_role,
        "source_message_id": source_message_id,
        "student_name": student_name,
        "reason": reason,
        "strategy": strategy,
        "trigger_type": trigger_type or "mention",
        "created_at": str(now_ts),
        "expire_at": str(expiry_ts),
    }
    ekey = mention_entry_key(eid)
    skey = mention_entry_status_key(eid)
    await redis_client.hset(ekey, mapping=entry)
    await redis_client.expire(ekey, MENTION_ENTRY_TTL_SECONDS)
    await redis_client.hset(
        skey,
        mapping={
            "entry_id": eid,
            "status": "queued",
            "reason": "",
            "task_id": "",
            "error": "",
            "updated_at": now_iso(),
        },
    )
    await redis_client.expire(skey, MENTION_ENTRY_TTL_SECONDS)
    await redis_client.zadd(MENTION_ENTRY_QUEUE_KEY, {eid: now_ts})
    return entry


async def get_mention_entry(entry_id: str) -> dict[str, str]:
    if not entry_id:
        return {}
    redis_client = get_redis_client()
    data = await redis_client.hgetall(mention_entry_key(entry_id))
    return {str(k): str(v) for k, v in (data or {}).items()}


async def pop_due_mention_entries(limit: int) -> list[dict[str, str]]:
    safe_limit = max(0, int(limit))
    if safe_limit <= 0:
        return []
    redis_client = get_redis_client()
    now_ts = time.time()
    # NOTE: Step-1 assumes single consumer; atomic multi-consumer pop can be added later via Lua.
    entry_ids = await redis_client.zrangebyscore(
        MENTION_ENTRY_QUEUE_KEY,
        min=0,
        max=now_ts,
        start=0,
        num=safe_limit,
    )
    if not entry_ids:
        return []
    await redis_client.zrem(MENTION_ENTRY_QUEUE_KEY, *entry_ids)
    entries: list[dict[str, str]] = []
    for entry_id in entry_ids:
        entry = await get_mention_entry(str(entry_id))
        if entry:
            entries.append(entry)
    return entries


async def mark_mention_entry_status(
    entry_id: str,
    status: str,
    reason: str | None = None,
    task_id: str | None = None,
    error: str | None = None,
) -> None:
    if not entry_id:
        return
    redis_client = get_redis_client()
    payload = {
        "entry_id": entry_id,
        "status": status,
        "reason": reason or "",
        "task_id": task_id or "",
        "error": error or "",
        "updated_at": now_iso(),
    }
    skey = mention_entry_status_key(entry_id)
    await redis_client.hset(skey, mapping=payload)
    await redis_client.expire(skey, MENTION_ENTRY_TTL_SECONDS)


async def remove_mention_entry_from_queue(entry_id: str) -> None:
    if not entry_id:
        return
    redis_client = get_redis_client()
    await redis_client.zrem(MENTION_ENTRY_QUEUE_KEY, entry_id)


async def get_mention_entry_queue_length() -> int:
    redis_client = get_redis_client()
    return int(await redis_client.zcard(MENTION_ENTRY_QUEUE_KEY))
