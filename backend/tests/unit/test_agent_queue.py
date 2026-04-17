import pytest

from app.agents import queue as agent_queue


class _FakeRedis:
    def __init__(self):
        self._z = {}

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


@pytest.mark.asyncio
async def test_enqueue_and_dequeue_orders_by_priority_then_time(monkeypatch):
    fake_redis = _FakeRedis()
    monkeypatch.setattr(agent_queue, "get_redis_client", lambda: fake_redis)

    await agent_queue.enqueue_task("r1", {"agent_role": "a", "priority": 2, "triggered_at": 2}, delay_seconds=0)
    await agent_queue.enqueue_task("r1", {"agent_role": "b", "priority": 0, "triggered_at": 3}, delay_seconds=0)
    await agent_queue.enqueue_task("r1", {"agent_role": "c", "priority": 0, "triggered_at": 1}, delay_seconds=0)

    tasks = await agent_queue.dequeue_tasks("r1")

    assert [t["agent_role"] for t in tasks] == ["c", "b", "a"]

