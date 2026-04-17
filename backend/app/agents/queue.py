from __future__ import annotations

import json
import time
import uuid

from app.db.redis_client import get_redis_client

QUEUE_KEY_PREFIX = "agent_queue"


def queue_key(room_id: str) -> str:
    return f"{QUEUE_KEY_PREFIX}:{room_id}"


def _normalize_task(task: dict) -> dict:
    normalized = dict(task)
    normalized.setdefault("task_id", str(uuid.uuid4()))
    normalized.setdefault("priority", 5)
    normalized.setdefault("triggered_at", time.time())
    return normalized


async def enqueue_task(room_id: str, task: dict, delay_seconds: float = 0.0) -> dict:
    redis_client = get_redis_client()
    execute_at = time.time() + max(0.0, float(delay_seconds))
    normalized = _normalize_task(task)
    task_json = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    await redis_client.zadd(queue_key(room_id), {task_json: execute_at})
    return normalized


async def dequeue_tasks(room_id: str) -> list[dict]:
    redis_client = get_redis_client()
    now = time.time()
    raw_tasks = await redis_client.zrangebyscore(queue_key(room_id), min=0, max=now)
    if not raw_tasks:
        return []

    await redis_client.zrem(queue_key(room_id), *raw_tasks)

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
    return parsed


async def requeue_task(room_id: str, task: dict, delay_seconds: float = 5.0) -> dict:
    return await enqueue_task(room_id, task, delay_seconds=delay_seconds)

