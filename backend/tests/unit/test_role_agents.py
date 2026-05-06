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
    status_updates = []

    monkeypatch.setattr(role_agents, "AsyncSessionLocal", factory)
    monkeypatch.setattr(role_agents.MessageService, "get_next_seq_num", _fake_next_seq)
    monkeypatch.setattr(role_agents, "stream_completion", _stream_tokens)
    monkeypatch.setattr(role_agents, "get_redis_client", lambda: redis)

    async def _fake_set_task_status(**kwargs):
        status_updates.append(kwargs)

    monkeypatch.setattr(role_agents, "set_task_status", _fake_set_task_status)

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
        task={"task_id": "task-role-success-1", "trigger_type": "mention", "reason": "r"},
    )

    stream_payloads = [e for e in events if e["type"] == "agent:stream"]
    assert stream_payloads
    assert stream_payloads[-1]["task_id"] == "task-role-success-1"
    stream_end = [e for e in events if e["type"] == "agent:stream_end"][-1]
    assert stream_end["task_id"] == "task-role-success-1"
    assert stream_end["status"] == "ok"
    assert stream_end["content"] == "hello world"
    assert stream_end["error"] is None
    assert redis.set_calls
    assert redis.sadd_calls
    assert any(s.get("status") == "replied" for s in status_updates)


@pytest.mark.asyncio
async def test_generate_and_push_generation_failure_includes_error(monkeypatch):
    init_session = _FakeSession()
    update_session = _FakeSession()
    factory = _SessionFactory([init_session, update_session])
    events = []
    status_updates = []

    monkeypatch.setattr(role_agents, "AsyncSessionLocal", factory)
    monkeypatch.setattr(role_agents.MessageService, "get_next_seq_num", _fake_next_seq)
    monkeypatch.setattr(role_agents, "stream_completion", _stream_fail)
    monkeypatch.setattr(role_agents, "get_redis_client", lambda: _FakeRedis())

    async def _fake_set_task_status(**kwargs):
        status_updates.append(kwargs)

    monkeypatch.setattr(role_agents, "set_task_status", _fake_set_task_status)

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
        task={"task_id": "task-role-failed-1", "trigger_type": "mention", "reason": "r"},
    )

    stream_end = [e for e in events if e["type"] == "agent:stream_end"][-1]
    assert stream_end["task_id"] == "task-role-failed-1"
    assert stream_end["status"] == "failed"
    assert stream_end["content"] == ""
    assert "Connection error." in (stream_end["error"] or "")
    assert any(s.get("status") == "failed" for s in status_updates)


@pytest.mark.asyncio
async def test_generate_and_push_db_update_failure_marks_failed(monkeypatch):
    init_session = _FakeSession()
    update_session = _FakeSession(fail_execute=True)
    factory = _SessionFactory([init_session, update_session])
    events = []
    status_updates = []

    monkeypatch.setattr(role_agents, "AsyncSessionLocal", factory)
    monkeypatch.setattr(role_agents.MessageService, "get_next_seq_num", _fake_next_seq)
    monkeypatch.setattr(role_agents, "stream_completion", _stream_tokens)
    monkeypatch.setattr(role_agents, "get_redis_client", lambda: _FakeRedis())

    async def _fake_set_task_status(**kwargs):
        status_updates.append(kwargs)

    monkeypatch.setattr(role_agents, "set_task_status", _fake_set_task_status)

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
        task={"task_id": "task-role-db-failed-1", "trigger_type": "mention", "reason": "r"},
    )

    stream_end = [e for e in events if e["type"] == "agent:stream_end"][-1]
    assert stream_end["task_id"] == "task-role-db-failed-1"
    assert stream_end["status"] == "failed"
    assert "DB update failed" in (stream_end["error"] or "")
    assert any(s.get("status") == "failed" for s in status_updates)


def test_devil_advocate_includes_skill_spec_in_system_prompt():
    agent = role_agents.DevilAdvocateAgent()
    prompt = agent.build_system_prompt(
        context={"task_description": "T", "task_workflow": "W", "members_info": "M", "current_phase": "P"},
        task={"reason": "R", "strategy": "S"},
    )

    assert "[Skill Spec]" in prompt
    assert "devil-advocate-skill" in prompt


def test_concept_explainer_registered_and_prompt_builds():
    assert "concept_explainer" in role_agents.ROLE_AGENTS
    agent = role_agents.ROLE_AGENTS["concept_explainer"]
    assert agent.ROLE_DISPLAY_NAME == "概念解释员"
    assert agent.PROMPT_FILE == "concept_explainer.txt"

    prompt = agent.build_system_prompt(
        context={
            "task_description": "三人小组围绕社会关键两难议题进行协作问题解决。",
            "task_workflow": "理解问题—提出立场—比较理由—形成方案。",
            "members_info": "学生A、学生B、学生C",
            "current_phase": "问题理解阶段",
        },
        task={
            "trigger_type": "mention",
            "reason": "学生主动询问难懂概念。",
            "strategy": "用通俗语言解释学生提到的概念，并给出一个可继续讨论的小问题。",
            "student_name": "学生A",
        },
    )

    assert "概念解释员" in prompt
    assert "降低认知负荷" in prompt
    assert "不要直接替学生生成最终答案" in prompt
    assert "通俗易懂" in prompt
    assert "问题理解阶段" in prompt
    assert "学生主动询问难懂概念。" in prompt
    assert "用通俗语言解释学生提到的概念，并给出一个可继续讨论的小问题。" in prompt
    assert "Do not provide a complete final answer for the group." in prompt
