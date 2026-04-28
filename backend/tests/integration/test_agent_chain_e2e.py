import json
from types import SimpleNamespace

import pytest

from app.agents import agent_worker, committee
from app.agents.queue import dequeue_tasks
from app.websocket import handlers


class _FakeRedis:
    def __init__(self):
        self.store = {}
        self.zsets = {}
        self.sets = {}
        self.published = []

    async def zadd(self, key, mapping):
        bucket = self.zsets.setdefault(key, [])
        for member, score in mapping.items():
            bucket.append((float(score), member))
        bucket.sort(key=lambda x: x[0])

    async def zrangebyscore(self, key, min=0, max=0):
        bucket = self.zsets.get(key, [])
        return [member for score, member in bucket if float(min) <= score <= float(max)]

    async def zrem(self, key, *members):
        bucket = self.zsets.get(key, [])
        to_remove = set(members)
        self.zsets[key] = [(s, m) for s, m in bucket if m not in to_remove]

    async def set(self, key, value, nx=False, ex=None):
        _ = ex
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    async def get(self, key):
        return self.store.get(key)

    async def exists(self, key):
        return key in self.store

    async def setex(self, key, ttl, value):
        _ = ttl
        self.store[key] = value

    async def incr(self, key):
        v = int(self.store.get(key, 0)) + 1
        self.store[key] = v
        return v

    async def expire(self, key, ttl):
        _ = ttl
        return key in self.store

    async def delete(self, key):
        self.store.pop(key, None)

    async def smembers(self, key):
        return list(self.sets.get(key, set()))

    async def sadd(self, key, value):
        self.sets.setdefault(key, set()).add(value)

    async def publish(self, channel, payload):
        self.published.append((channel, payload))


class _CfgTiming:
    global_intervention_limit_per_hour = 99
    agent_cooldown_seconds = 1
    room_auto_intervention_cooldown_seconds = 1
    silence_trigger_enabled = True


class _CfgAuto:
    committee_enabled = True


class _Cfg:
    timing = _CfgTiming()
    auto_speak = _CfgAuto()


class _MentionCfg:
    enabled = True
    priority = 0
    max_mentions_per_message = 3


class _HandlersCfg:
    mention = _MentionCfg()


class _DummyAgent:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.calls = []

    async def generate_and_push(self, **kwargs):
        self.calls.append(kwargs)
        payload = {
            "type": "agent:stream_end",
            "agent_role": kwargs["task"]["agent_role"],
            "status": "ok",
            "trigger_type": kwargs["task"].get("trigger_type"),
        }
        await self.redis.publish(f"room:{kwargs['room_id']}", json.dumps(payload, ensure_ascii=False))


@pytest.mark.asyncio
async def test_committee_to_worker_to_agent_publish_chain(monkeypatch):
    fake_redis = _FakeRedis()
    room_id = "room-chain-1"

    monkeypatch.setattr("app.agents.queue.get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(committee, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(agent_worker, "get_redis_client", lambda: fake_redis)

    async def _msgs(_room_id, limit=50):
        _ = limit
        return [{"display_name": "A", "content": "hello"}]

    async def _members(_room_id):
        return [{"name": "A"}, {"name": "B"}]

    async def _ctx(_room_id):
        return {"current_phase": "middle", "recent_interventions": []}

    async def _analyst(_messages, _members):
        return {"score": 0.5}

    monkeypatch.setattr(committee, "get_recent_messages", _msgs)
    monkeypatch.setattr(committee, "get_room_members", _members)
    monkeypatch.setattr(committee, "get_room_context", _ctx)
    monkeypatch.setattr(committee.basic_committee.cognitive_analyst, "analyze", _analyst)
    monkeypatch.setattr(committee.basic_committee.behavioral_analyst, "analyze", _analyst)
    monkeypatch.setattr(committee.basic_committee.emotional_analyst, "analyze", _analyst)
    monkeypatch.setattr(committee.basic_committee.social_analyst, "analyze", _analyst)

    monkeypatch.setattr(
        committee.basic_committee.dispatcher,
        "dispatch",
        lambda **_: {
            "should_intervene": True,
            "selected_agent_role": "facilitator",
            "trigger_type": "committee",
            "reason": "Need alignment.",
            "strategy": "Ask one focused question.",
            "priority": 1,
            "target_dimension": "social",
            "evidence": ["missing_cps_skill=D1"],
            "current_phase": "middle",
        },
    )

    async def _save_snapshot(**_kwargs):
        return "snap-1"

    async def _publish_update(**_kwargs):
        return None

    monkeypatch.setattr(committee.basic_committee, "_save_snapshot", _save_snapshot)
    monkeypatch.setattr(committee.basic_committee, "_publish_analysis_update", _publish_update)

    await committee.basic_committee.analyze_and_dispatch(room_id)

    tasks = await dequeue_tasks(room_id)
    assert len(tasks) == 1
    task = tasks[0]
    assert task["trigger_type"] == "committee"
    assert task["agent_role"] == "facilitator"
    assert task["reason"] == "Need alignment."
    assert task["strategy"] == "Ask one focused question."

    dummy_agent = _DummyAgent(fake_redis)
    monkeypatch.setattr(agent_worker, "ROLE_AGENTS", {"facilitator": dummy_agent})
    monkeypatch.setattr(agent_worker, "get_agent_settings", lambda: _Cfg())

    async def _worker_ctx(_room_id):
        return {"task_description": "T", "members_info": "A,B", "current_phase": "middle"}

    async def _worker_history(_room_id):
        return [{"display_name": "A", "content": "hello"}]

    monkeypatch.setattr(agent_worker, "get_room_context", _worker_ctx)
    monkeypatch.setattr(agent_worker, "get_recent_messages", _worker_history)

    worker = agent_worker.AgentWorker()
    await worker._execute_task(room_id, task)

    assert len(dummy_agent.calls) == 1
    sent_task = dummy_agent.calls[0]["task"]
    assert sent_task["reason"] == "Need alignment."
    assert sent_task["strategy"] == "Ask one focused question."

    stream_end = [
        json.loads(payload)
        for channel, payload in fake_redis.published
        if channel == f"room:{room_id}" and "agent:stream_end" in payload
    ]
    assert stream_end, "expected agent:stream_end publish"
    assert stream_end[-1]["status"] == "ok"
    assert stream_end[-1]["trigger_type"] == "committee"


@pytest.mark.asyncio
async def test_mention_to_queue_to_worker_to_agent_publish_chain(monkeypatch):
    fake_redis = _FakeRedis()
    room_id = "room-chain-mention-1"
    source_message_id = "msg-123"

    monkeypatch.setattr("app.agents.queue.get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(agent_worker, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(handlers, "get_agent_settings", lambda: _HandlersCfg())
    monkeypatch.setattr(handlers, "ROLE_AGENTS", {"encourager": object()})

    class _Manager:
        def __init__(self):
            self.events = []

        async def broadcast_to_room(self, _room_id, payload):
            self.events.append(payload)

    manager = _Manager()
    monkeypatch.setattr(handlers, "manager", manager)

    user = SimpleNamespace(display_name="Student A")
    await handlers._trigger_mentions(room_id, source_message_id, user, ["encourager"])

    tasks = await dequeue_tasks(room_id)
    assert len(tasks) == 1
    task = tasks[0]
    assert task["trigger_type"] == "mention"
    assert task["agent_role"] == "encourager"
    assert task["source_message_id"] == source_message_id
    assert task["target_dimension"] == "user_request"

    dummy_agent = _DummyAgent(fake_redis)
    monkeypatch.setattr(agent_worker, "ROLE_AGENTS", {"encourager": dummy_agent})
    monkeypatch.setattr(agent_worker, "get_agent_settings", lambda: _Cfg())

    async def _worker_ctx(_room_id):
        return {"task_description": "T", "members_info": "A,B", "current_phase": "middle"}

    async def _worker_history(_room_id):
        return [{"display_name": "A", "content": "please help"}]

    monkeypatch.setattr(agent_worker, "get_room_context", _worker_ctx)
    monkeypatch.setattr(agent_worker, "get_recent_messages", _worker_history)

    worker = agent_worker.AgentWorker()
    await worker._execute_task(room_id, task)

    assert len(dummy_agent.calls) == 1
    sent_task = dummy_agent.calls[0]["task"]
    assert sent_task["trigger_type"] == "mention"
    assert sent_task["source_message_id"] == source_message_id

    stream_end = [
        json.loads(payload)
        for channel, payload in fake_redis.published
        if channel == f"room:{room_id}" and "agent:stream_end" in payload
    ]
    assert stream_end, "expected mention-chain agent:stream_end publish"
    assert stream_end[-1]["status"] == "ok"
    assert stream_end[-1]["trigger_type"] == "mention"
