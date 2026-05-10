import asyncio
import json
import statistics
import time
import uuid
from datetime import datetime, timezone

import pytest

from app.agents import agent_worker
from app.agents import queue as agent_queue
from app.agents.role_agents import ROLE_AGENTS
from app.models.user import User, UserRole
from app.websocket import handlers


class _FakeRedisQueue:
    def __init__(self):
        self.zsets = {}
        self.hashes = {}
        self.published = []
        self.kv = {}

    async def zadd(self, key, mapping):
        bucket = self.zsets.setdefault(key, [])
        for raw, score in mapping.items():
            bucket.append((float(score), raw))

    async def zcard(self, key):
        return len(self.zsets.get(key, []))

    async def zrangebyscore(self, key, min=0, max=0):  # noqa: A002
        result = []
        remaining = []
        for score, raw in self.zsets.get(key, []):
            if float(min) <= score <= float(max):
                result.append(raw)
            else:
                remaining.append((score, raw))
        # keep original list; zrem handles removal explicitly
        self.zsets[key] = self.zsets.get(key, [])
        return result

    async def zrange(self, key, start, end, withscores=False):
        items = sorted(self.zsets.get(key, []), key=lambda x: x[0])
        if end == -1:
            sliced = items[start:]
        else:
            sliced = items[start : end + 1]
        if withscores:
            return [(raw, score) for score, raw in sliced]
        return [raw for score, raw in sliced]

    async def zrem(self, key, *members):
        member_set = set(members)
        self.zsets[key] = [(s, r) for (s, r) in self.zsets.get(key, []) if r not in member_set]

    async def hset(self, key, mapping):
        self.hashes[key] = {str(k): str(v) for k, v in mapping.items()}

    async def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    async def expire(self, _key, _ttl):
        return True

    async def publish(self, channel, message):
        self.published.append((channel, message))

    async def exists(self, _key):
        return _key in self.kv

    async def set(self, _key, _value, nx=False, ex=None):
        _ = ex
        if nx and _key in self.kv:
            return False
        self.kv[_key] = str(_value)
        return True

    async def get(self, _key):
        return self.kv.get(_key)

    async def delete(self, _key):
        self.kv.pop(_key, None)
        return True

    async def setex(self, _key, _ttl, _value):
        self.kv[_key] = str(_value)
        return True

    async def ttl(self, _key):
        return 1


class _Cfg:
    class mention:
        enabled = True
        priority = 0
        max_mentions_per_message = 10

    class timing:
        mention_entry_enabled = False
        mention_entry_queue_max_wait_sec = 60
        mention_entry_rate_per_sec = 1000
        agent_response_timeout_seconds = 30
        agent_cooldown_seconds = 0
        room_auto_intervention_cooldown_seconds = 0
        silence_trigger_enabled = False
        silence_threshold_seconds = 60
        warmup_minutes = 0
        rule_trigger_marker_ttl_seconds = 180
        agent_global_concurrency_limit = 1

    auto_speak = None


class _DummySocraticAgent:
    def __init__(self, sleep_seconds: float = 0.0):
        self.sleep_seconds = sleep_seconds
        self.calls = []

    async def generate_and_push(self, **kwargs):
        started = time.perf_counter()
        self.calls.append(
            {
                "room_id": kwargs.get("room_id"),
                "source_message_id": kwargs.get("source_message_id"),
                "trigger_type": kwargs.get("trigger_type"),
                "started_perf": started,
            }
        )
        if self.sleep_seconds > 0:
            await asyncio.sleep(self.sleep_seconds)
        self.calls[-1]["finished_perf"] = time.perf_counter()


def _student(name: str) -> User:
    return User(
        id=uuid.uuid4(),
        username=name,
        password_hash="x",
        display_name=name,
        role=UserRole.student,
    )


def _print_diag(prefix: str, data: dict):
    print(f"[{prefix}] {json.dumps(data, ensure_ascii=False)}")


@pytest.mark.asyncio
async def test_single_mode_frequent_mentions_are_coalesced_after_fix(monkeypatch):
    fake_redis = _FakeRedisQueue()
    ack_events = []
    queued_events = []

    async def _mode_single(_room_id):
        return "single"

    async def _broadcast(_room_id, payload):
        if payload.get("type") == "agent:ack":
            ack_events.append(payload)
        if payload.get("type") == "agent:queued":
            queued_events.append(payload)

    monkeypatch.setattr(handlers, "get_room_agent_mode", _mode_single)
    monkeypatch.setattr(handlers, "get_agent_settings", lambda: _Cfg())
    monkeypatch.setattr(handlers.manager, "broadcast_to_room", _broadcast)
    monkeypatch.setattr(agent_queue, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(agent_queue, "get_room_agent_mode", _mode_single)

    students = [_student("s1"), _student("s2"), _student("s3")]
    total_mentions = 0
    for i in range(5):
        for stu in students:
            total_mentions += 1
            await handlers._trigger_mentions(
                room_id="room-single-repro",
                source_message_id=f"m-{stu.username}-{i}",
                user=stu,
                mentions=["socratic"],
            )

    queue_len = await fake_redis.zcard(agent_queue.queue_key("room-single-repro"))
    status_values = list(fake_redis.hashes.values())
    status_dist = {}
    for item in status_values:
        st = item.get("status", "")
        status_dist[st] = status_dist.get(st, 0) + 1

    _print_diag(
        "single_high_freq_enqueue",
        {
            "total_mentions": total_mentions,
            "ack_events": len(ack_events),
            "queued_events": len(queued_events),
            "actual_socratic_tasks": queue_len,
            "task_status_distribution": status_dist,
            "queue_depth_after": queue_len,
        },
    )

    assert total_mentions == 15
    assert len(ack_events) == 15
    assert len(queued_events) <= 15
    assert queue_len <= 3
    assert status_dist.get("queued", 0) <= 3


@pytest.mark.asyncio
async def test_single_mode_socratic_worker_serialization_under_burst(monkeypatch):
    fake_redis = _FakeRedisQueue()
    dummy_agent = _DummySocraticAgent(sleep_seconds=0.05)
    status_calls = []

    async def _mode_single(_room_id):
        return "single"

    async def _capture_status(**kwargs):
        status_calls.append(kwargs)

    async def _fake_room_context(_room_id):
        return {}

    async def _fake_recent(_room_id):
        return []

    monkeypatch.setattr(agent_queue, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(agent_queue, "get_room_agent_mode", _mode_single)
    monkeypatch.setattr(agent_worker, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(agent_worker, "get_room_agent_mode", _mode_single)
    monkeypatch.setattr(agent_worker, "get_agent_settings", lambda: _Cfg())
    monkeypatch.setattr(agent_worker, "set_task_status", _capture_status)
    monkeypatch.setattr(agent_worker, "ROLE_AGENTS", {"socratic": dummy_agent})
    monkeypatch.setattr(agent_worker, "get_room_context", _fake_room_context)
    monkeypatch.setattr(agent_worker, "get_recent_messages", _fake_recent)

    room_id = str(uuid.uuid4())
    for i in range(12):
        await agent_queue.enqueue_task(
            room_id,
            {
                "room_id": room_id,
                "agent_role": "socratic",
                "reason": "burst",
                "strategy": "burst",
                "priority": 0,
                "trigger_type": "mention",
                "source_message_id": f"src-{i}",
                "triggered_at": time.time(),
            },
        )

    tasks = await agent_queue.dequeue_tasks(room_id)
    t0 = time.perf_counter()
    worker = agent_worker.AgentWorker()
    for t in tasks:
        await worker._execute_task(room_id, t)
    elapsed = time.perf_counter() - t0

    waits = []
    for t in tasks:
        st = fake_redis.hashes.get(agent_queue.task_status_key(str(t["task_id"])), {})
        queued_at = st.get("queued_at", "")
        running_at = st.get("running_at", "")
        if queued_at and running_at:
            q = datetime.fromisoformat(queued_at)
            r = datetime.fromisoformat(running_at)
            waits.append((r - q).total_seconds())

    _print_diag(
        "single_worker_serialization",
        {
            "total_tasks": len(tasks),
            "completed_calls": len(dummy_agent.calls),
            "elapsed_seconds": round(elapsed, 4),
            "average_wait_seconds": round(sum(waits) / len(waits), 4) if waits else None,
            "max_wait_seconds": round(max(waits), 4) if waits else None,
            "worker_concurrency_assumption": 1,
        },
    )

    assert len(tasks) == 1
    assert len(dummy_agent.calls) == 1
    assert elapsed < 12 * 0.05 * 0.8


@pytest.mark.asyncio
async def test_single_mode_running_socratic_keeps_only_one_pending_followup(monkeypatch):
    fake_redis = _FakeRedisQueue()
    dummy_agent = _DummySocraticAgent(sleep_seconds=0.2)

    async def _mode_single(_room_id):
        return "single"

    async def _fake_room_context(_room_id):
        return {}

    async def _fake_recent(_room_id):
        return []

    monkeypatch.setattr(agent_queue, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(agent_queue, "get_room_agent_mode", _mode_single)
    monkeypatch.setattr(handlers, "get_room_agent_mode", _mode_single)
    monkeypatch.setattr(handlers, "get_agent_settings", lambda: _Cfg())
    monkeypatch.setattr(handlers.manager, "broadcast_to_room", lambda *_args, **_kwargs: asyncio.sleep(0))
    monkeypatch.setattr(agent_worker, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(agent_worker, "get_room_agent_mode", _mode_single)
    monkeypatch.setattr(agent_worker, "get_agent_settings", lambda: _Cfg())
    monkeypatch.setattr(agent_worker, "ROLE_AGENTS", {"socratic": dummy_agent})
    monkeypatch.setattr(agent_worker, "get_room_context", _fake_room_context)
    monkeypatch.setattr(agent_worker, "get_recent_messages", _fake_recent)

    room_id = str(uuid.uuid4())
    first = await agent_queue.enqueue_task(
        room_id,
        {
            "room_id": room_id,
            "agent_role": "socratic",
            "reason": "first",
            "strategy": "first",
            "priority": 0,
            "trigger_type": "mention",
            "source_message_id": "first",
            "triggered_at": time.time(),
        },
    )
    assert first is not None
    tasks = await agent_queue.dequeue_tasks(room_id)
    assert len(tasks) == 1

    worker = agent_worker.AgentWorker()
    exec_task = asyncio.create_task(worker._execute_task(room_id, tasks[0]))
    await asyncio.sleep(0.05)

    students = [_student("f1"), _student("f2"), _student("f3")]
    for i in range(5):
        for stu in students:
            await handlers._trigger_mentions(
                room_id=room_id,
                source_message_id=f"run-{stu.username}-{i}",
                user=stu,
                mentions=["socratic"],
            )

    queued_after_burst = await fake_redis.zcard(agent_queue.queue_key(room_id))
    assert queued_after_burst <= 1

    await exec_task
    followups = await agent_queue.dequeue_tasks(room_id)
    assert len(followups) <= 1
    if followups:
        followup = followups[0]
        assert int(followup.get("merged_count") or 1) > 1
        assert str(followup.get("latest_message_id") or "").startswith("run-")
        source_ids = followup.get("source_message_ids") or []
        assert isinstance(source_ids, list)
        assert len(source_ids) == 15

    _print_diag(
        "single_running_pending_followup",
        {
            "queued_after_burst": queued_after_burst,
            "followup_tasks_after_running": len(followups),
            "followup_merged_count": int(followups[0].get("merged_count") or 1) if followups else 0,
        },
    )


@pytest.mark.asyncio
async def test_single_mode_frequent_mentions_hit_busy_or_cooldown(monkeypatch):
    sent_frames = []

    class _DummyWs:
        async def send_json(self, payload):
            sent_frames.append(payload)

    async def _save(_db, _room_id, _uid, content, _mentions, **_kwargs):
        class _Msg:
            def __init__(self, text: str):
                self.id = uuid.uuid4()
                self.seq_num = 1
                self.content = text
                self.created_at = datetime.now(timezone.utc)

        return _Msg(content)

    async def _broadcast(_room_id, _payload):
        return None

    async def _no_trigger(*_args, **_kwargs):
        return None

    async def _mode_single(_room_id):
        return "single"

    async def _busy(_room_id):
        return True

    async def _no_cooling(_rid, _mentions):
        return None

    monkeypatch.setattr(handlers.MessageService, "save_student_message", _save)
    monkeypatch.setattr(handlers.manager, "broadcast_to_room", _broadcast)
    monkeypatch.setattr(handlers.trigger_detector, "check_monopoly", _no_trigger)
    monkeypatch.setattr(handlers, "_trigger_mentions", _no_trigger)
    monkeypatch.setattr(handlers, "get_room_agent_mode", _mode_single)
    monkeypatch.setattr(handlers, "_is_agent_pipeline_busy", _busy)
    monkeypatch.setattr(handlers, "_first_cooling_mention_role", _no_cooling)

    user = _student("s_busy")
    await handlers.handle_chat_message(
        data={"type": "chat:message", "content": "@socratic hi", "mentions": ["socratic"]},
        room_id=str(uuid.uuid4()),
        user=user,
        db=object(),
        websocket=_DummyWs(),
    )

    block_reasons = [f.get("reason") for f in sent_frames if f.get("type") == "agent:mention_blocked"]
    _print_diag(
        "single_busy_cooldown",
        {
            "total_frames": len(sent_frames),
            "mention_blocked_count": len(block_reasons),
            "block_reasons": block_reasons,
        },
    )

    assert len(block_reasons) >= 1
    assert "agent_busy" in block_reasons


@pytest.mark.asyncio
async def test_single_mode_coalescing_does_not_call_real_llm(monkeypatch):
    # If anything in this repro path tries to hit real LLM, fail immediately.
    # The test uses a mocked Socratic agent and never touches real model APIs.
    called_real_llm = {"called": False}

    async def _forbid_real_llm(*_args, **_kwargs):
        called_real_llm["called"] = True
        raise AssertionError("Real LLM must not be called in repro tests")

    dummy_agent = _DummySocraticAgent(sleep_seconds=0.0)
    fake_redis = _FakeRedisQueue()

    async def _mode_single(_room_id):
        return "single"

    async def _fake_room_context(_room_id):
        return {}

    async def _fake_recent(_room_id):
        return []

    monkeypatch.setattr(agent_queue, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(agent_queue, "get_room_agent_mode", _mode_single)
    monkeypatch.setattr(agent_worker, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(agent_worker, "get_room_agent_mode", _mode_single)
    monkeypatch.setattr(agent_worker, "get_agent_settings", lambda: _Cfg())
    monkeypatch.setattr(agent_worker, "ROLE_AGENTS", {"socratic": dummy_agent})
    monkeypatch.setattr(agent_worker, "get_room_context", _fake_room_context)
    monkeypatch.setattr(agent_worker, "get_recent_messages", _fake_recent)

    # Guard common LLM path in case someone rewires agent internals.
    monkeypatch.setattr("app.agents.llm_client.stream_completion", _forbid_real_llm, raising=False)

    room_id = str(uuid.uuid4())
    await agent_queue.enqueue_task(
        room_id,
        {
            "room_id": room_id,
            "agent_role": "socratic",
            "reason": "repro",
            "strategy": "repro",
            "priority": 0,
            "trigger_type": "mention",
            "source_message_id": "src-1",
            "triggered_at": time.time(),
        },
    )
    tasks = await agent_queue.dequeue_tasks(room_id)
    worker = agent_worker.AgentWorker()
    for t in tasks:
        await worker._execute_task(room_id, t)

    _print_diag(
        "single_no_real_llm",
        {
            "tasks_processed": len(tasks),
            "dummy_agent_calls": len(dummy_agent.calls),
            "real_llm_called": called_real_llm["called"],
        },
    )

    assert len(dummy_agent.calls) == 1
    assert called_real_llm["called"] is False
    assert ROLE_AGENTS.get("socratic") is not None


@pytest.mark.asyncio
async def test_single_mode_reply_latency_breakdown_queue_wait_vs_generation_time(monkeypatch):
    fake_redis = _FakeRedisQueue()
    generation_sleep = 0.2
    dummy_agent = _DummySocraticAgent(sleep_seconds=generation_sleep)
    called_real_llm = {"called": False}

    mention_times = {}
    enqueue_times = {}
    worker_start_times = {}
    reply_times = {}
    task_to_source = {}

    async def _mode_single(_room_id):
        return "single"

    async def _fake_room_context(_room_id):
        return {}

    async def _fake_recent(_room_id):
        return []

    async def _forbid_real_llm(*_args, **_kwargs):
        called_real_llm["called"] = True
        raise AssertionError("Real LLM must not be called in repro tests")

    original_enqueue = agent_queue.enqueue_task

    async def _enqueue_with_timestamp(room_id, task, delay_seconds=0.0):
        now_ts = time.perf_counter()
        result = await original_enqueue(room_id, task, delay_seconds=delay_seconds)
        if result is not None:
            task_id = str(result.get("task_id") or "")
            src = str(result.get("source_message_id") or "")
            enqueue_times[task_id] = now_ts
            task_to_source[task_id] = src
        return result

    async def _capture_status(**kwargs):
        if kwargs.get("status") == "running":
            task_id = str(kwargs.get("task_id") or "")
            worker_start_times[task_id] = time.perf_counter()

    monkeypatch.setattr(agent_queue, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(agent_queue, "get_room_agent_mode", _mode_single)
    monkeypatch.setattr(handlers, "get_room_agent_mode", _mode_single)
    monkeypatch.setattr(handlers, "get_agent_settings", lambda: _Cfg())
    monkeypatch.setattr(handlers.manager, "broadcast_to_room", lambda *_args, **_kwargs: asyncio.sleep(0))
    monkeypatch.setattr(handlers, "enqueue_task", _enqueue_with_timestamp)
    monkeypatch.setattr(agent_worker, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(agent_worker, "get_room_agent_mode", _mode_single)
    monkeypatch.setattr(agent_worker, "get_agent_settings", lambda: _Cfg())
    monkeypatch.setattr(agent_worker, "set_task_status", _capture_status)
    monkeypatch.setattr(agent_worker, "ROLE_AGENTS", {"socratic": dummy_agent})
    monkeypatch.setattr(agent_worker, "get_room_context", _fake_room_context)
    monkeypatch.setattr(agent_worker, "get_recent_messages", _fake_recent)
    monkeypatch.setattr("app.agents.llm_client.stream_completion", _forbid_real_llm, raising=False)

    students = [_student("stu_a"), _student("stu_b"), _student("stu_c")]
    room_id = str(uuid.uuid4())
    total_mentions = 0

    for i in range(5):
        for stu in students:
            total_mentions += 1
            source_message_id = f"lat-{stu.username}-{i}"
            mention_times[source_message_id] = time.perf_counter()
            await handlers._trigger_mentions(
                room_id=room_id,
                source_message_id=source_message_id,
                user=stu,
                mentions=["socratic"],
            )

    tasks = await agent_queue.dequeue_tasks(room_id)
    t0 = time.perf_counter()
    worker = agent_worker.AgentWorker()
    for t in tasks:
        await worker._execute_task(room_id, t)
    total_elapsed = time.perf_counter() - t0

    for c in dummy_agent.calls:
        src = str(c.get("source_message_id") or "")
        if src:
            reply_times[src] = float(c["finished_perf"])

    queue_waits = []
    generation_times = []
    total_latencies = []

    for t in tasks:
        task_id = str(t.get("task_id") or "")
        src = task_to_source.get(task_id, "")
        if not src:
            continue
        mention_ts = mention_times.get(src)
        enqueue_ts = enqueue_times.get(task_id)
        start_ts = worker_start_times.get(task_id)
        reply_ts = reply_times.get(src)
        if None in (mention_ts, enqueue_ts, start_ts, reply_ts):
            continue

        q_wait = start_ts - enqueue_ts
        g_time = reply_ts - start_ts
        total_lat = reply_ts - mention_ts
        queue_waits.append(q_wait)
        generation_times.append(g_time)
        total_latencies.append(total_lat)

    assert called_real_llm["called"] is False
    assert len(tasks) <= 3
    assert len(total_latencies) == len(tasks)

    first_reply_latency = min(total_latencies)
    median_reply_latency = statistics.median(total_latencies)
    last_reply_latency = max(total_latencies)
    avg_queue_wait = statistics.mean(queue_waits)
    max_queue_wait = max(queue_waits)
    avg_generation = statistics.mean(generation_times)
    max_generation = max(generation_times)
    queue_wait_ratio = avg_queue_wait / (avg_queue_wait + avg_generation) if (avg_queue_wait + avg_generation) > 0 else 0.0

    _print_diag(
        "single_latency_breakdown",
        {
            "total_mentions": total_mentions,
            "actual_socratic_tasks": len(tasks),
            "mock_generation_time": generation_sleep,
            "first_reply_latency": round(first_reply_latency, 4),
            "median_reply_latency": round(median_reply_latency, 4),
            "last_reply_latency": round(last_reply_latency, 4),
            "average_queue_wait": round(avg_queue_wait, 4),
            "max_queue_wait": round(max_queue_wait, 4),
            "average_generation_time": round(avg_generation, 4),
            "max_generation_time": round(max_generation, 4),
            "queue_wait_ratio": round(queue_wait_ratio, 4),
            "total_elapsed": round(total_elapsed, 4),
            "real_llm_called": called_real_llm["called"],
        },
    )

    # Repro diagnosis assertions:
    assert avg_generation == pytest.approx(generation_sleep, rel=0.35)
    assert max_generation == pytest.approx(generation_sleep, rel=0.5)
    assert last_reply_latency < 3.0760
    assert max_queue_wait < 2.8612
    assert total_elapsed < 3.0760


@pytest.mark.asyncio
async def test_single_mode_coalescing_preserves_latest_message_context(monkeypatch):
    fake_redis = _FakeRedisQueue()

    async def _mode_single(_room_id):
        return "single"

    monkeypatch.setattr(agent_queue, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(agent_queue, "get_room_agent_mode", _mode_single)
    monkeypatch.setattr(handlers, "get_room_agent_mode", _mode_single)
    monkeypatch.setattr(handlers, "get_agent_settings", lambda: _Cfg())
    monkeypatch.setattr(handlers.manager, "broadcast_to_room", lambda *_args, **_kwargs: asyncio.sleep(0))

    stu = _student("ctx")
    room_id = str(uuid.uuid4())
    for i in range(1, 6):
        await handlers._trigger_mentions(
            room_id=room_id,
            source_message_id=f"question-{i}",
            user=stu,
            mentions=["socratic"],
        )

    tasks = await agent_queue.dequeue_tasks(room_id)
    assert len(tasks) == 1
    merged_task = tasks[0]
    assert str(merged_task.get("latest_message_id")) == "question-5"
    source_ids = merged_task.get("source_message_ids") or []
    assert isinstance(source_ids, list)
    assert source_ids == ["question-1", "question-2", "question-3", "question-4", "question-5"]


@pytest.mark.asyncio
async def test_single_mode_running_key_cleared_even_when_worker_fails(monkeypatch):
    fake_redis = _FakeRedisQueue()

    class _FailingSocratic:
        async def generate_and_push(self, **_kwargs):
            raise RuntimeError("synthetic failure")

    async def _mode_single(_room_id):
        return "single"

    async def _fake_room_context(_room_id):
        return {}

    async def _fake_recent(_room_id):
        return []

    async def _capture_status(**_kwargs):
        return None

    monkeypatch.setattr(agent_queue, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(agent_queue, "get_room_agent_mode", _mode_single)
    monkeypatch.setattr(agent_worker, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(agent_worker, "get_room_agent_mode", _mode_single)
    monkeypatch.setattr(agent_worker, "get_agent_settings", lambda: _Cfg())
    monkeypatch.setattr(agent_worker, "set_task_status", _capture_status)
    monkeypatch.setattr(agent_worker, "ROLE_AGENTS", {"socratic": _FailingSocratic()})
    monkeypatch.setattr(agent_worker, "get_room_context", _fake_room_context)
    monkeypatch.setattr(agent_worker, "get_recent_messages", _fake_recent)

    room_id = str(uuid.uuid4())
    task = await agent_queue.enqueue_task(
        room_id,
        {
            "room_id": room_id,
            "agent_role": "socratic",
            "reason": "fail",
            "strategy": "fail",
            "priority": 0,
            "trigger_type": "mention",
            "source_message_id": "msg-fail",
            "triggered_at": time.time(),
        },
    )
    assert task is not None
    tasks = await agent_queue.dequeue_tasks(room_id)
    assert len(tasks) == 1

    worker = agent_worker.AgentWorker()
    with pytest.raises(RuntimeError):
        await worker._execute_task(room_id, tasks[0])

    running_key = agent_queue.running_task_key(room_id, "socratic")
    assert await fake_redis.get(running_key) is None


@pytest.mark.asyncio
async def test_multi_mode_not_affected_by_single_socratic_coalescing(monkeypatch):
    fake_redis = _FakeRedisQueue()

    async def _mode_multi(_room_id):
        return "multi"

    monkeypatch.setattr(agent_queue, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(agent_queue, "get_room_agent_mode", _mode_multi)

    room_id = str(uuid.uuid4())
    for i in range(15):
        task = await agent_queue.enqueue_task(
            room_id,
            {
                "room_id": room_id,
                "agent_role": "facilitator",
                "reason": "multi-regression",
                "strategy": "multi-regression",
                "priority": 0,
                "trigger_type": "mention",
                "source_message_id": f"multi-{i}",
                "triggered_at": time.time(),
            },
        )
        assert task is not None

    queue_len = await fake_redis.zcard(agent_queue.queue_key(room_id))
    assert queue_len == 15


@pytest.mark.asyncio
async def test_single_mode_non_socratic_role_not_enter_socratic_coalescing(monkeypatch):
    fake_redis = _FakeRedisQueue()

    async def _mode_single(_room_id):
        return "single"

    monkeypatch.setattr(agent_queue, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(agent_queue, "get_room_agent_mode", _mode_single)

    room_id = str(uuid.uuid4())
    task = await agent_queue.enqueue_task(
        room_id,
        {
            "room_id": room_id,
            "agent_role": "facilitator",
            "reason": "blocked",
            "strategy": "blocked",
            "priority": 0,
            "trigger_type": "mention",
            "source_message_id": "blocked-1",
            "triggered_at": time.time(),
        },
    )
    assert task is None
    queue_len = await fake_redis.zcard(agent_queue.queue_key(room_id))
    assert queue_len == 0


@pytest.mark.asyncio
async def test_single_mode_concurrent_mentions_do_not_create_duplicate_socratic_tasks(monkeypatch):
    fake_redis = _FakeRedisQueue()

    async def _mode_single(_room_id):
        return "single"

    monkeypatch.setattr(agent_queue, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(agent_queue, "get_room_agent_mode", _mode_single)

    room_id = str(uuid.uuid4())

    async def _enqueue_one(i: int):
        return await agent_queue.enqueue_task(
            room_id,
            {
                "room_id": room_id,
                "agent_role": "socratic",
                "reason": "concurrent",
                "strategy": "concurrent",
                "priority": 0,
                "trigger_type": "mention",
                "source_message_id": f"con-{i}",
                "triggered_at": time.time(),
            },
        )

    await asyncio.gather(*[_enqueue_one(i) for i in range(20)])

    tasks = await agent_queue.dequeue_tasks(room_id)
    assert len(tasks) <= 1
    assert len(tasks) >= 1
    task = tasks[0]
    assert int(task.get("merged_count") or 1) == 20
    assert str(task.get("latest_message_id") or "") == "con-19"
    source_ids = task.get("source_message_ids") or []
    assert isinstance(source_ids, list)
    assert len(source_ids) <= 20


@pytest.mark.asyncio
async def test_single_mode_coalesced_source_message_ids_are_bounded(monkeypatch):
    fake_redis = _FakeRedisQueue()

    async def _mode_single(_room_id):
        return "single"

    monkeypatch.setattr(agent_queue, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(agent_queue, "get_room_agent_mode", _mode_single)

    room_id = str(uuid.uuid4())
    for i in range(1, 101):
        task = await agent_queue.enqueue_task(
            room_id,
            {
                "room_id": room_id,
                "agent_role": "socratic",
                "reason": "bounded",
                "strategy": "bounded",
                "priority": 0,
                "trigger_type": "mention",
                "source_message_id": f"q-{i}",
                "triggered_at": time.time(),
            },
        )
        assert task is not None

    tasks = await agent_queue.dequeue_tasks(room_id)
    assert len(tasks) == 1
    merged = tasks[0]
    assert int(merged.get("merged_count") or 1) == 100
    assert str(merged.get("latest_message_id") or "") == "q-100"
    source_ids = merged.get("source_message_ids") or []
    assert isinstance(source_ids, list)
    assert len(source_ids) <= 50
    assert source_ids[0] == "q-51"
    assert source_ids[-1] == "q-100"
    assert bool(merged.get("truncated_source_message_ids")) is True
    assert int(merged.get("dropped_source_message_count") or 0) == 50
