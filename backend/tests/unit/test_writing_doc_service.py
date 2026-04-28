import pytest

from app.services import writing_doc_service


class _FakeRedis:
    def __init__(self):
        self._kv = {}
        self._counters = {}
        self._lists = {}

    async def get(self, key):
        return self._kv.get(key)

    async def set(self, key, value):
        self._kv[key] = value

    async def incr(self, key):
        current = int(self._counters.get(key, 0)) + 1
        self._counters[key] = current
        return current

    async def lpush(self, key, value):
        self._lists.setdefault(key, [])
        self._lists[key].insert(0, value)

    async def ltrim(self, key, start, end):
        values = self._lists.get(key, [])
        self._lists[key] = values[start : end + 1]

    async def lrange(self, key, start, end):
        values = self._lists.get(key, [])
        return values[start : end + 1]


@pytest.mark.asyncio
async def test_get_writing_doc_state_returns_empty_when_missing(monkeypatch):
    fake_redis = _FakeRedis()
    monkeypatch.setattr(writing_doc_service, "get_redis_client", lambda: fake_redis)

    state = await writing_doc_service.get_writing_doc_state("r1")

    assert state["content"] == ""
    assert state["version"] == 0
    assert state["updated_at"] is None
    assert state["updated_by"] is None


@pytest.mark.asyncio
async def test_apply_writing_doc_update_increments_version(monkeypatch):
    fake_redis = _FakeRedis()
    monkeypatch.setattr(writing_doc_service, "get_redis_client", lambda: fake_redis)

    state1 = await writing_doc_service.apply_writing_doc_update("r2", "hello", "u1")
    state2 = await writing_doc_service.apply_writing_doc_update("r2", "world", "u2")

    assert state1["version"] == 1
    assert state2["version"] == 2
    assert state2["content"] == "world"
    assert state2["updated_by"] == "u2"


@pytest.mark.asyncio
async def test_apply_update_with_stale_base_returns_current_without_apply(monkeypatch):
    fake_redis = _FakeRedis()
    monkeypatch.setattr(writing_doc_service, "get_redis_client", lambda: fake_redis)

    state1 = await writing_doc_service.apply_writing_doc_update("r3", "v1", "u1")
    stale_state, applied = await writing_doc_service.apply_writing_doc_update_with_base_version(
        "r3",
        "stale",
        "u2",
        base_version=0,
    )

    assert state1["version"] == 1
    assert applied is False
    assert stale_state["content"] == "v1"
    assert stale_state["version"] == 1


@pytest.mark.asyncio
async def test_change_log_records_update_and_save(monkeypatch):
    fake_redis = _FakeRedis()
    monkeypatch.setattr(writing_doc_service, "get_redis_client", lambda: fake_redis)

    s1, applied1 = await writing_doc_service.apply_writing_doc_update_with_base_version(
        "r4", "A", "u1", "Alice", base_version=0
    )
    s2, applied2 = await writing_doc_service.apply_writing_doc_update_with_base_version(
        "r4", "B", "u2", "Bob", base_version=1
    )
    await writing_doc_service.save_writing_doc_version("r4", "u2", "Bob")
    logs = await writing_doc_service.get_writing_doc_change_log("r4", limit=10)

    assert applied1 is True
    assert applied2 is True
    assert s1["version"] == 1
    assert s2["version"] == 2
    assert len(logs) == 3
    assert logs[0]["action"] == "save_checkpoint"
    assert logs[0]["actor_display_name"] == "Bob"
    assert logs[1]["action"] == "update"
    assert logs[2]["action"] == "update"
