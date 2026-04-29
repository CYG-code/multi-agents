import asyncio

import pytest

from app.agents import agent_worker


class _FakeRedis:
    def __init__(self):
        self.keys = set()
        self.setex_calls = []
        self.values = {}
        self.delete_calls = []

    async def get(self, _key):
        return self.values.get(_key)

    async def exists(self, key):
        return key in self.keys

    async def set(self, _key, _value, nx=False, ex=None):
        _ = ex
        if nx and _key in self.values:
            return False
        self.values[_key] = _value
        return True

    async def setex(self, key, ttl, value):
        self.setex_calls.append((key, ttl, value))
        self.keys.add(key)

    async def incr(self, _key):
        return 1

    async def expire(self, _key, _ttl):
        return True

    async def delete(self, _key):
        self.delete_calls.append(_key)
        self.values.pop(_key, None)
        return True


class _FakeRedisWithTtl:
    def __init__(self):
        self.now = 0
        self.values = {}
        self.expire_at = {}
        self.setex_calls = []
        self.delete_calls = []

    def advance(self, seconds: int):
        self.now += int(seconds)

    def _is_expired(self, key):
        exp = self.expire_at.get(key)
        return exp is not None and self.now >= exp

    async def get(self, key):
        if self._is_expired(key):
            self.values.pop(key, None)
            self.expire_at.pop(key, None)
            return None
        return self.values.get(key)

    async def exists(self, key):
        if self._is_expired(key):
            self.values.pop(key, None)
            self.expire_at.pop(key, None)
            return False
        return key in self.values

    async def set(self, key, value, nx=False, ex=None):
        if nx and await self.exists(key):
            return False
        self.values[key] = value
        if ex is not None:
            self.expire_at[key] = self.now + int(ex)
        return True

    async def setex(self, key, ttl, value):
        self.values[key] = value
        self.expire_at[key] = self.now + int(ttl)
        self.setex_calls.append((key, ttl, value))
        return True

    async def incr(self, key):
        current = int((await self.get(key)) or 0) + 1
        self.values[key] = str(current)
        return current

    async def expire(self, key, ttl):
        if key not in self.values:
            return False
        self.expire_at[key] = self.now + int(ttl)
        return True

    async def delete(self, key):
        self.delete_calls.append(key)
        self.values.pop(key, None)
        self.expire_at.pop(key, None)
        return True


class _CfgTiming:
    global_intervention_limit_per_hour = 99
    agent_cooldown_seconds = 60
    room_auto_intervention_cooldown_seconds = 180
    agent_response_timeout_seconds = 1


class _Cfg:
    timing = _CfgTiming()
    auto_speak = None


class _DummyAgent:
    async def generate_and_push(self, **_kwargs):
        return None


class _SlowAgent:
    async def generate_and_push(self, **_kwargs):
        await asyncio.sleep(6)


class _ErrorAgent:
    async def generate_and_push(self, **_kwargs):
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_worker_drops_auto_task_when_room_auto_cooldown(monkeypatch):
    fake_redis = _FakeRedis()
    fake_redis.keys.add("cooldown:r1:auto_intervention")
    requeued = []

    async def _fake_requeue(_room_id, _task, delay_seconds=0):
        requeued.append(delay_seconds)

    monkeypatch.setattr(agent_worker, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(agent_worker, "get_agent_settings", lambda: _Cfg())
    monkeypatch.setattr(agent_worker, "requeue_task", _fake_requeue)
    monkeypatch.setattr(agent_worker, "ROLE_AGENTS", {"encourager": _DummyAgent()})

    worker = agent_worker.AgentWorker()
    await worker._execute_task("r1", {"agent_role": "encourager", "trigger_type": "committee"})

    assert requeued == []


@pytest.mark.asyncio
async def test_worker_requeues_mention_task_on_role_cooldown(monkeypatch):
    fake_redis = _FakeRedis()
    fake_redis.keys.add("cooldown:r2:encourager")
    requeued = []

    async def _fake_requeue(_room_id, _task, delay_seconds=0):
        requeued.append(delay_seconds)

    monkeypatch.setattr(agent_worker, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(agent_worker, "get_agent_settings", lambda: _Cfg())
    monkeypatch.setattr(agent_worker, "requeue_task", _fake_requeue)
    monkeypatch.setattr(agent_worker, "ROLE_AGENTS", {"encourager": _DummyAgent()})

    worker = agent_worker.AgentWorker()
    await worker._execute_task("r2", {"agent_role": "encourager", "trigger_type": "mention"})

    assert requeued == [10]


@pytest.mark.asyncio
async def test_worker_requeues_task_when_agent_generation_times_out(monkeypatch):
    fake_redis = _FakeRedis()
    requeued = []

    async def _fake_requeue(_room_id, _task, delay_seconds=0):
        requeued.append(delay_seconds)

    async def _fake_context(_room_id):
        return {"current_phase": "middle"}

    async def _fake_history(_room_id):
        return []

    monkeypatch.setattr(agent_worker, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(agent_worker, "get_agent_settings", lambda: _Cfg())
    monkeypatch.setattr(agent_worker, "requeue_task", _fake_requeue)
    monkeypatch.setattr(agent_worker, "get_room_context", _fake_context)
    monkeypatch.setattr(agent_worker, "get_recent_messages", _fake_history)
    monkeypatch.setattr(agent_worker, "ROLE_AGENTS", {"resource_finder": _SlowAgent()})

    worker = agent_worker.AgentWorker()
    await worker._execute_task("r3", {"agent_role": "resource_finder", "trigger_type": "mention"})

    assert requeued == [5]
    assert "room:r3:agent_lock" in fake_redis.delete_calls


@pytest.mark.asyncio
async def test_worker_multiple_mentions_same_role_second_requeued(monkeypatch):
    fake_redis = _FakeRedisWithTtl()
    requeued = []
    called = {"count": 0}

    class _CfgTimingShort:
        global_intervention_limit_per_hour = 99
        agent_cooldown_seconds = 12
        room_auto_intervention_cooldown_seconds = 180
        agent_response_timeout_seconds = 1

    class _CfgShort:
        timing = _CfgTimingShort()
        auto_speak = None

    class _CountAgent:
        async def generate_and_push(self, **_kwargs):
            called["count"] += 1
            return None

    async def _fake_requeue(_room_id, _task, delay_seconds=0):
        requeued.append(delay_seconds)

    async def _fake_context(_room_id):
        return {"current_phase": "middle"}

    async def _fake_history(_room_id):
        return []

    monkeypatch.setattr(agent_worker, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(agent_worker, "get_agent_settings", lambda: _CfgShort())
    monkeypatch.setattr(agent_worker, "requeue_task", _fake_requeue)
    monkeypatch.setattr(agent_worker, "get_room_context", _fake_context)
    monkeypatch.setattr(agent_worker, "get_recent_messages", _fake_history)
    monkeypatch.setattr(agent_worker, "ROLE_AGENTS", {"resource_finder": _CountAgent()})

    worker = agent_worker.AgentWorker()
    task = {"agent_role": "resource_finder", "trigger_type": "mention"}

    await worker._execute_task("r4", task)
    await worker._execute_task("r4", task)
    fake_redis.advance(10)
    await worker._execute_task("r4", task)
    fake_redis.advance(3)
    await worker._execute_task("r4", task)

    assert called["count"] == 2
    assert requeued == [10, 10]
    assert "cooldown:r4:resource_finder" in fake_redis.values


@pytest.mark.asyncio
async def test_worker_drops_task_when_hourly_limit_hit(monkeypatch):
    fake_redis = _FakeRedis()
    fake_redis.values["interventions:r5:0"] = "99"
    requeued = []
    called = {"count": 0}

    class _CfgTimingLimited:
        global_intervention_limit_per_hour = 2
        agent_cooldown_seconds = 5
        room_auto_intervention_cooldown_seconds = 180
        agent_response_timeout_seconds = 1

    class _CfgLimited:
        timing = _CfgTimingLimited()
        auto_speak = None

    class _CountAgent:
        async def generate_and_push(self, **_kwargs):
            called["count"] += 1

    async def _fake_requeue(_room_id, _task, delay_seconds=0):
        requeued.append(delay_seconds)

    monkeypatch.setattr(agent_worker, "time", type("T", (), {"time": staticmethod(lambda: 0)})())
    monkeypatch.setattr(agent_worker, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(agent_worker, "get_agent_settings", lambda: _CfgLimited())
    monkeypatch.setattr(agent_worker, "requeue_task", _fake_requeue)
    monkeypatch.setattr(agent_worker, "ROLE_AGENTS", {"resource_finder": _CountAgent()})

    worker = agent_worker.AgentWorker()
    await worker._execute_task("r5", {"agent_role": "resource_finder", "trigger_type": "mention"})

    assert called["count"] == 0
    assert requeued == []


@pytest.mark.asyncio
async def test_worker_requeues_when_agent_lock_not_acquired(monkeypatch):
    fake_redis = _FakeRedis()
    fake_redis.values["room:r6:agent_lock"] = "other-worker"
    requeued = []

    async def _fake_requeue(_room_id, _task, delay_seconds=0):
        requeued.append(delay_seconds)

    monkeypatch.setattr(agent_worker, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(agent_worker, "get_agent_settings", lambda: _Cfg())
    monkeypatch.setattr(agent_worker, "requeue_task", _fake_requeue)
    monkeypatch.setattr(agent_worker, "ROLE_AGENTS", {"resource_finder": _DummyAgent()})

    worker = agent_worker.AgentWorker()
    await worker._execute_task("r6", {"agent_role": "resource_finder", "trigger_type": "mention"})

    assert requeued == [5]


@pytest.mark.asyncio
async def test_worker_releases_lock_when_agent_raises(monkeypatch):
    fake_redis = _FakeRedis()

    async def _fake_context(_room_id):
        return {"current_phase": "middle"}

    async def _fake_history(_room_id):
        return []

    monkeypatch.setattr(agent_worker, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(agent_worker, "get_agent_settings", lambda: _Cfg())
    monkeypatch.setattr(agent_worker, "get_room_context", _fake_context)
    monkeypatch.setattr(agent_worker, "get_recent_messages", _fake_history)
    monkeypatch.setattr(agent_worker, "ROLE_AGENTS", {"resource_finder": _ErrorAgent()})

    worker = agent_worker.AgentWorker()
    with pytest.raises(RuntimeError):
        await worker._execute_task("r7", {"agent_role": "resource_finder", "trigger_type": "mention"})

    assert "room:r7:agent_lock" in fake_redis.delete_calls

