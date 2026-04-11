from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agents import role_agents


class _FakeSession:
    def __init__(self, fail_execute: bool = False):
        self.fail_execute = fail_execute
        self.added = []
        self.commits = 0
        self.executed = []

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def execute(self, stmt):
        if self.fail_execute:
            raise RuntimeError("db broken")
        self.executed.append(stmt)
        return SimpleNamespace()


class _SessionFactory:
    def __init__(self, sessions):
        self._sessions = list(sessions)

    def __call__(self):
        session = self._sessions.pop(0)

        class _Ctx:
            async def __aenter__(self):
                return session

            async def __aexit__(self, exc_type, exc, tb):
                return False

        return _Ctx()


class _FakeRedis:
    def __init__(self):
        self.set_calls = []
        self.sadd_calls = []

    async def set(self, key, value):
        self.set_calls.append((key, value))

    async def sadd(self, key, value):
        self.sadd_calls.append((key, value))


async def _fake_next_seq(_room_id):
    return 101


async def _stream_tokens(*_args, **_kwargs):
    yield "hello"
    yield " world"


async def _stream_fail(*_args, **_kwargs):
    raise RuntimeError("Connection error.")
    yield  # pragma: no cover


@pytest.mark.asyncio
async def test_generate_and_push_success(monkeypatch):
    init_session = _FakeSession()
    update_session = _FakeSession()
    factory = _SessionFactory([init_session, update_session])
    redis = _FakeRedis()
    events = []

    monkeypatch.setattr(role_agents, "AsyncSessionLocal", factory)
    monkeypatch.setattr(role_agents.MessageService, "get_next_seq_num", _fake_next_seq)
    monkeypatch.setattr(role_agents, "stream_completion", _stream_tokens)
    monkeypatch.setattr(role_agents, "get_redis_client", lambda: redis)

    async def _capture(_self, _room_id, payload):
        events.append(payload)

    monkeypatch.setattr(role_agents.FacilitatorAgent, "_broadcast", _capture)

    agent = role_agents.FacilitatorAgent()
    await agent.generate_and_push(
        room_id="room-1",
        context={"task_description": "T", "members_info": "A", "current_phase": "P"},
        history=[{"display_name": "A", "content": "Hi"}],
        source_message_id="msg-1",
        trigger_type="mention",
    )

    stream_end = [e for e in events if e["type"] == "agent:stream_end"][-1]
    assert stream_end["status"] == "ok"
    assert stream_end["content"] == "hello world"
    assert stream_end["error"] is None
    assert redis.set_calls
    assert redis.sadd_calls


@pytest.mark.asyncio
async def test_generate_and_push_generation_failure_includes_error(monkeypatch):
    init_session = _FakeSession()
    update_session = _FakeSession()
    factory = _SessionFactory([init_session, update_session])
    events = []

    monkeypatch.setattr(role_agents, "AsyncSessionLocal", factory)
    monkeypatch.setattr(role_agents.MessageService, "get_next_seq_num", _fake_next_seq)
    monkeypatch.setattr(role_agents, "stream_completion", _stream_fail)
    monkeypatch.setattr(role_agents, "get_redis_client", lambda: _FakeRedis())

    async def _capture(_self, _room_id, payload):
        events.append(payload)

    monkeypatch.setattr(role_agents.FacilitatorAgent, "_broadcast", _capture)

    agent = role_agents.FacilitatorAgent()
    await agent.generate_and_push(
        room_id="room-1",
        context={"task_description": "T", "members_info": "A", "current_phase": "P"},
        history=[{"display_name": "A", "content": "Hi"}],
        source_message_id="msg-2",
        trigger_type="mention",
    )

    stream_end = [e for e in events if e["type"] == "agent:stream_end"][-1]
    assert stream_end["status"] == "failed"
    assert stream_end["content"] == ""
    assert "Connection error." in (stream_end["error"] or "")


@pytest.mark.asyncio
async def test_generate_and_push_db_update_failure_marks_failed(monkeypatch):
    init_session = _FakeSession()
    update_session = _FakeSession(fail_execute=True)
    factory = _SessionFactory([init_session, update_session])
    events = []

    monkeypatch.setattr(role_agents, "AsyncSessionLocal", factory)
    monkeypatch.setattr(role_agents.MessageService, "get_next_seq_num", _fake_next_seq)
    monkeypatch.setattr(role_agents, "stream_completion", _stream_tokens)
    monkeypatch.setattr(role_agents, "get_redis_client", lambda: _FakeRedis())

    async def _capture(_self, _room_id, payload):
        events.append(payload)

    monkeypatch.setattr(role_agents.FacilitatorAgent, "_broadcast", _capture)

    agent = role_agents.FacilitatorAgent()
    await agent.generate_and_push(
        room_id="room-1",
        context={"task_description": "T", "members_info": "A", "current_phase": "P"},
        history=[{"display_name": "A", "content": "Hi"}],
        source_message_id="msg-3",
        trigger_type="mention",
    )

    stream_end = [e for e in events if e["type"] == "agent:stream_end"][-1]
    assert stream_end["status"] == "failed"
    assert "DB update failed" in (stream_end["error"] or "")
