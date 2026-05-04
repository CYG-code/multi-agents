import pytest

from app.analysis import scheduler


class _FakeRedis:
    def __init__(self, active_rooms, values=None):
        self._active_rooms = active_rooms
        self._values = values or {}
        self._locks = set()
        self._ttls = {}

    async def smembers(self, _key):
        return list(self._active_rooms)

    async def get(self, key):
        return self._values.get(key)

    async def exists(self, key):
        return key in self._locks

    async def setex(self, key, _ttl, _val):
        self._locks.add(key)
        self._ttls[key] = int(_ttl)


class _Timing:
    silence_trigger_enabled = True
    silence_threshold_seconds = 120
    warmup_minutes = 3
    rule_trigger_marker_ttl_seconds = 180
    room_auto_intervention_cooldown_seconds = 180


class _AutoSpeak:
    facilitator_silence_enabled = True


class _Cfg:
    timing = _Timing()
    auto_speak = _AutoSpeak()


@pytest.mark.asyncio
async def test_check_silence_prioritizes_last_activity_time(monkeypatch):
    now = 1_000.0
    room_id = "room-1"
    fake_redis = _FakeRedis(
        active_rooms=[room_id],
        values={
            f"room:{room_id}:last_activity_time": str(now - 30),   # active recently
            f"room:{room_id}:last_msg_time": str(now - 400),       # old chat
        },
    )
    enqueued = []

    async def _fake_enqueue(room_id_arg, payload):
        enqueued.append((room_id_arg, payload))

    async def _fake_elapsed(_room_id):
        return 1_000.0

    monkeypatch.setattr(scheduler, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(scheduler, "get_agent_settings", lambda: _Cfg())
    monkeypatch.setattr(scheduler, "enqueue_task", _fake_enqueue)
    monkeypatch.setattr(scheduler.time, "time", lambda: now)
    monkeypatch.setattr(scheduler, "get_elapsed_seconds_from_timer_start", _fake_elapsed)

    await scheduler.check_silence()

    assert enqueued == []


@pytest.mark.asyncio
async def test_check_silence_falls_back_to_last_msg_time(monkeypatch):
    now = 2_000.0
    room_id = "room-2"
    fake_redis = _FakeRedis(
        active_rooms=[room_id],
        values={
            f"room:{room_id}:last_msg_time": str(now - 300),  # no last_activity_time
        },
    )
    enqueued = []

    async def _fake_enqueue(room_id_arg, payload):
        enqueued.append((room_id_arg, payload))

    async def _fake_elapsed(_room_id):
        return 1_000.0

    monkeypatch.setattr(scheduler, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(scheduler, "get_agent_settings", lambda: _Cfg())
    monkeypatch.setattr(scheduler, "enqueue_task", _fake_enqueue)
    monkeypatch.setattr(scheduler.time, "time", lambda: now)
    monkeypatch.setattr(scheduler, "get_elapsed_seconds_from_timer_start", _fake_elapsed)

    await scheduler.check_silence()

    assert len(enqueued) == 1
    assert enqueued[0][0] == room_id
    assert enqueued[0][1]["trigger_type"] == "silence"
    assert await fake_redis.exists(f"recent_rule_trigger:{room_id}:silence")


@pytest.mark.asyncio
async def test_check_silence_skips_when_recent_rule_trigger_exists(monkeypatch):
    now = 3_000.0
    room_id = "room-3"
    fake_redis = _FakeRedis(
        active_rooms=[room_id],
        values={
            f"room:{room_id}:last_activity_time": str(now - 400),
        },
    )
    fake_redis._locks.add(f"recent_rule_trigger:{room_id}:silence")
    enqueued = []

    async def _fake_enqueue(room_id_arg, payload):
        enqueued.append((room_id_arg, payload))

    async def _fake_elapsed(_room_id):
        return 1_000.0

    monkeypatch.setattr(scheduler, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(scheduler, "get_agent_settings", lambda: _Cfg())
    monkeypatch.setattr(scheduler, "enqueue_task", _fake_enqueue)
    monkeypatch.setattr(scheduler.time, "time", lambda: now)
    monkeypatch.setattr(scheduler, "get_elapsed_seconds_from_timer_start", _fake_elapsed)

    await scheduler.check_silence()

    assert enqueued == []


@pytest.mark.asyncio
async def test_check_silence_sets_recent_rule_ttl_with_longer_window(monkeypatch):
    now = 4_000.0
    room_id = "room-4"
    fake_redis = _FakeRedis(
        active_rooms=[room_id],
        values={
            f"room:{room_id}:last_activity_time": str(now - 400),
        },
    )
    enqueued = []

    async def _fake_enqueue(room_id_arg, payload):
        enqueued.append((room_id_arg, payload))

    async def _fake_elapsed(_room_id):
        return 1_000.0

    monkeypatch.setattr(scheduler, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(scheduler, "get_agent_settings", lambda: _Cfg())
    monkeypatch.setattr(scheduler, "enqueue_task", _fake_enqueue)
    monkeypatch.setattr(scheduler.time, "time", lambda: now)
    monkeypatch.setattr(scheduler, "get_elapsed_seconds_from_timer_start", _fake_elapsed)

    await scheduler.check_silence()

    recent_key = f"recent_rule_trigger:{room_id}:silence"
    lock_key = f"trigger_lock:{room_id}:silence"
    assert len(enqueued) == 1
    assert await fake_redis.exists(recent_key)
    assert await fake_redis.exists(lock_key)
    assert fake_redis._ttls[recent_key] > _Timing.rule_trigger_marker_ttl_seconds


@pytest.mark.asyncio
async def test_check_silence_trigger_lock_still_prevents_enqueue(monkeypatch):
    now = 5_000.0
    room_id = "room-5"
    fake_redis = _FakeRedis(
        active_rooms=[room_id],
        values={
            f"room:{room_id}:last_activity_time": str(now - 500),
        },
    )
    fake_redis._locks.add(f"trigger_lock:{room_id}:silence")
    enqueued = []

    async def _fake_enqueue(room_id_arg, payload):
        enqueued.append((room_id_arg, payload))

    async def _fake_elapsed(_room_id):
        return 1_000.0

    monkeypatch.setattr(scheduler, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(scheduler, "get_agent_settings", lambda: _Cfg())
    monkeypatch.setattr(scheduler, "enqueue_task", _fake_enqueue)
    monkeypatch.setattr(scheduler.time, "time", lambda: now)
    monkeypatch.setattr(scheduler, "get_elapsed_seconds_from_timer_start", _fake_elapsed)

    await scheduler.check_silence()

    assert enqueued == []
