import types

import pytest

from app.agents import context_builder


class _FakeAsyncSessionCtx:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSession:
    async def get(self, _model, _id):
        return None

    async def execute(self, _stmt):
        class _Result:
            def fetchall(self):
                return [("学生A",), ("学生B",)]

        return _Result()


@pytest.mark.asyncio
async def test_get_room_context_fallback(monkeypatch):
    monkeypatch.setattr(
        context_builder,
        "AsyncSessionLocal",
        lambda: _FakeAsyncSessionCtx(_FakeSession()),
    )

    result = await context_builder.get_room_context("room-1")

    assert result["task_description"] == "讨论一个社会议题"
    assert result["members_info"] == "学生A、学生B"
    assert result["current_phase"] == "第一阶段：问题分析"

