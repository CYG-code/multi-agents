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
async def test_history_and_restore(monkeypatch):
    fake_redis = _FakeRedis()
    monkeypatch.setattr(writing_doc_service, "get_redis_client", lambda: fake_redis)

    s1 = await writing_doc_service.apply_writing_doc_update("r4", "A", "u1", "Alice")
    await writing_doc_service.save_writing_doc_version("r4", "u1", "Alice")
    s2 = await writing_doc_service.apply_writing_doc_update("r4", "B", "u2", "Bob")
    await writing_doc_service.save_writing_doc_version("r4", "u2", "Bob")
    await writing_doc_service.restore_writing_doc_version("r4", s1["version"], "u3", "Teacher")
    await writing_doc_service.save_writing_doc_version("r4", "u3", "Teacher")
    await writing_doc_service.apply_writing_doc_update("r4", "C", "u1", "Alice")
    await writing_doc_service.save_writing_doc_version("r4", "u1", "Alice")
    await writing_doc_service.apply_writing_doc_update("r4", "D", "u1", "Alice")
    await writing_doc_service.save_writing_doc_version("r4", "u1", "Alice")

    history = await writing_doc_service.get_writing_doc_history("r4", limit=10)
    restore_target_version = history[-1]["version"]
    restore_target_content = history[-1]["content"]
    restored = await writing_doc_service.restore_writing_doc_version("r4", restore_target_version, "u9", "Teacher2")

    assert s1["version"] == 1
    assert s2["version"] == 2
    assert len(history) == 3
    assert all(item.get("saved_at") for item in history)
    assert restored["version"] >= 3
    assert restored["content"] == restore_target_content
