import pytest

from app.analysis import triggers


class _FakeRedis:
    def __init__(self):
        self._lists = {}
        self._locks = set()

    async def lpush(self, key, value):
        self._lists.setdefault(key, [])
        self._lists[key].insert(0, value)

    async def ltrim(self, key, start, end):
        self._lists[key] = self._lists.get(key, [])[start : end + 1]

    async def expire(self, _key, _ttl):
        return True

    async def lrange(self, key, start, end):
        values = self._lists.get(key, [])
        if end == -1:
            return values[start:]
        return values[start : end + 1]

    async def exists(self, key):
        return key in self._locks

    async def setex(self, key, _ttl, _val):
        self._locks.add(key)


@pytest.mark.asyncio
async def test_check_monopoly_enqueues_once(monkeypatch):
    fake_redis = _FakeRedis()
    calls = []

    async def _fake_enqueue(room_id, task, delay_seconds=0):
        calls.append((room_id, task, delay_seconds))
        return task

    class _Thresholds:
        monopoly_message_count = 3

    class _Cfg:
        thresholds = _Thresholds()

    monkeypatch.setattr(triggers, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(triggers, "enqueue_task", _fake_enqueue)
    monkeypatch.setattr(triggers, "get_agent_settings", lambda: _Cfg())

    detector = triggers.TriggerDetector()
    await detector.check_monopoly("room-1", "u1")
    await detector.check_monopoly("room-1", "u1")
    await detector.check_monopoly("room-1", "u1")
    await detector.check_monopoly("room-1", "u1")

    assert len(calls) == 1
    assert calls[0][1]["agent_role"] == "encourager"
