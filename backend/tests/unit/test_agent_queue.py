import pytest

from app.agents import queue as agent_queue


class _FakeRedis:
    def __init__(self):
        self._z = {}
        self._h = {}
        self._exp = {}

    async def zadd(self, key, mapping):
        bucket = self._z.setdefault(key, {})
        for member, score in mapping.items():
            bucket[member] = score

    async def zrangebyscore(self, key, min, max):
        bucket = self._z.get(key, {})
        items = [(member, score) for member, score in bucket.items() if min <= score <= max]
        items.sort(key=lambda x: x[1])
        return [member for member, _ in items]

    async def zrem(self, key, *members):
        bucket = self._z.get(key, {})
        for member in members:
            bucket.pop(member, None)

    async def zcard(self, key):
        return len(self._z.get(key, {}))

    async def hset(self, key, mapping):
        bucket = self._h.setdefault(key, {})
        bucket.update({str(k): str(v) for k, v in mapping.items()})
        return True

    async def hgetall(self, key):
        return self._h.get(key, {})

    async def expire(self, _key, _ttl):
        self._exp[_key] = _ttl
        return True


@pytest.mark.asyncio
async def test_enqueue_and_dequeue_orders_by_priority_then_time(monkeypatch):
    fake_redis = _FakeRedis()
    monkeypatch.setattr(agent_queue, "get_redis_client", lambda: fake_redis)

    await agent_queue.enqueue_task("r1", {"agent_role": "a", "priority": 2, "triggered_at": 2}, delay_seconds=0)
    await agent_queue.enqueue_task("r1", {"agent_role": "b", "priority": 0, "triggered_at": 3}, delay_seconds=0)
    await agent_queue.enqueue_task("r1", {"agent_role": "c", "priority": 0, "triggered_at": 1}, delay_seconds=0)

    tasks = await agent_queue.dequeue_tasks("r1")

    assert [t["agent_role"] for t in tasks] == ["c", "b", "a"]


@pytest.mark.asyncio
async def test_enqueue_writes_queued_task_status(monkeypatch):
    fake_redis = _FakeRedis()
    monkeypatch.setattr(agent_queue, "get_redis_client", lambda: fake_redis)

    task = await agent_queue.enqueue_task(
        "room-status",
        {
            "task_id": "task-status-1",
            "agent_role": "facilitator",
            "trigger_type": "mention",
            "reason": "test reason",
            "priority": 1,
            "triggered_at": 1.0,
            "source_message_id": "msg-1",
        },
    )

    key = agent_queue.task_status_key(task["task_id"])
    status = fake_redis._h.get(key, {})
    assert status.get("status") == "queued"
    assert status.get("task_id") == "task-status-1"
    assert status.get("room_id") == "room-status"
    assert status.get("agent_role") == "facilitator"
    assert status.get("source_message_id") == "msg-1"
    assert fake_redis._exp.get(key) == agent_queue.TASK_STATUS_TTL_SECONDS
