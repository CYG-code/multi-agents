import pytest

from app.agents import agent_worker


class _FakeRedis:
    def __init__(self):
        self.keys = set()
        self.setex_calls = []

    async def get(self, _key):
        return None

    async def exists(self, key):
        return key in self.keys

    async def set(self, _key, _value, nx=False, ex=None):
        _ = nx, ex
        return True

    async def setex(self, key, ttl, value):
        self.setex_calls.append((key, ttl, value))
        self.keys.add(key)

    async def incr(self, _key):
        return 1

    async def expire(self, _key, _ttl):
        return True

    async def delete(self, _key):
        return True


class _CfgTiming:
    global_intervention_limit_per_hour = 99
    agent_cooldown_seconds = 60
    room_auto_intervention_cooldown_seconds = 180


class _Cfg:
    timing = _CfgTiming()
    auto_speak = None


class _DummyAgent:
    async def generate_and_push(self, **_kwargs):
        return None


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

