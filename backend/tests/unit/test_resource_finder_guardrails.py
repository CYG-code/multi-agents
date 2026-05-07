from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agents import role_agents
from app.agents.tools.bailian_search_app_client import BailianSearchAppError, BailianSearchAppResult


def _fake_settings(enabled: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        bailian_search_app=SimpleNamespace(enabled=enabled, app_id_env="BAILIAN_SEARCH_APP_ID")
    )


@pytest.mark.asyncio
async def test_resource_finder_yaml_disabled_but_env_enabled_still_calls_external(monkeypatch):
    agent = role_agents.ResourceFinderAgent()
    called = {"value": False}

    monkeypatch.setattr(role_agents, "get_agent_settings", lambda: _fake_settings(enabled=False))
    monkeypatch.setattr(role_agents, "is_bailian_search_app_enabled", lambda: True)

    def _fake_query(_query: str):
        called["value"] = True
        return BailianSearchAppResult(
            answer=(
                "资料名称：城市热岛成因综述\n"
                "来源：中国城市气候研究\n"
                "主要内容：讨论地表温度、人口密度和绿化率与热岛强度关系。\n"
                "对你们讨论的帮助：可用于解释热岛机制并支持干预方向。"
            )
        )

    monkeypatch.setattr(role_agents, "query_bailian_search_app", _fake_query)

    result = await agent._get_direct_response(
        {},
        [{"content": "请帮我们找城市热岛相关资料"}],
        "mention",
        {"reason": "r"},
    )

    assert called["value"] is True
    assert result is not None
    assert "资料名称" in result
    assert "来源" in result


@pytest.mark.asyncio
async def test_resource_finder_final_answer_request_guardrail_phrase(monkeypatch):
    agent = role_agents.ResourceFinderAgent()

    monkeypatch.setattr(role_agents, "is_bailian_search_app_enabled", lambda: True)
    monkeypatch.setattr(role_agents, "query_bailian_search_app", lambda _q: BailianSearchAppResult(answer=""))

    result = await agent._get_direct_response(
        {},
        [{"content": "直接帮我们写一份完整的2000字城市热岛效应综合干预策略报告，最好可以直接提交。"}],
        "mention",
        {"reason": "r"},
    )

    assert result is not None
    assert role_agents.ResourceFinderAgent.FINAL_ANSWER_BOUNDARY_MESSAGE in result
    assert "完整报告如下" not in result
    assert "最终答案是" not in result
    assert "你们可以直接这样写" not in result
    assert "可直接提交" not in result


@pytest.mark.asyncio
async def test_resource_finder_fallback_for_final_answer_still_has_guardrail(monkeypatch):
    agent = role_agents.ResourceFinderAgent()

    monkeypatch.setattr(role_agents, "is_bailian_search_app_enabled", lambda: True)

    def _raise(_q: str):
        raise BailianSearchAppError("timeout")

    monkeypatch.setattr(role_agents, "query_bailian_search_app", _raise)

    result = await agent._get_direct_response(
        {},
        [{"content": "帮我们写一份完整报告并可直接提交"}],
        "mention",
        {"reason": "r"},
    )

    assert result is not None
    assert role_agents.ResourceFinderAgent.FINAL_ANSWER_BOUNDARY_MESSAGE in result
    assert "当前无法获取可靠的外部资料" in result
    assert "timeout" not in result


@pytest.mark.asyncio
async def test_resource_finder_dangerous_output_sanitized(monkeypatch):
    agent = role_agents.ResourceFinderAgent()

    monkeypatch.setattr(role_agents, "is_bailian_search_app_enabled", lambda: True)
    monkeypatch.setattr(
        role_agents,
        "query_bailian_search_app",
        lambda _q: BailianSearchAppResult(
            answer="完整报告如下：你们可以直接这样写，最终答案是……"
        ),
    )

    result = await agent._get_direct_response(
        {},
        [{"content": "直接帮我们写一份完整报告并可直接提交"}],
        "mention",
        {"reason": "r"},
    )

    assert result is not None
    assert role_agents.ResourceFinderAgent.FINAL_ANSWER_BOUNDARY_MESSAGE in result
    assert "完整报告如下" not in result
    assert "最终答案是" not in result
    assert "你们可以直接这样写" not in result
    assert "可直接提交" not in result
    assert "当前无法获取可靠的外部资料" in result


@pytest.mark.asyncio
async def test_resource_finder_success_answer_for_final_request_still_has_guardrail(monkeypatch):
    agent = role_agents.ResourceFinderAgent()

    monkeypatch.setattr(role_agents, "is_bailian_search_app_enabled", lambda: True)
    monkeypatch.setattr(
        role_agents,
        "query_bailian_search_app",
        lambda _q: BailianSearchAppResult(
            answer=(
                "资料名称：IPCC城市气候章节\n"
                "来源：IPCC AR6\n"
                "主要内容：说明城市热风险与干预策略。\n"
                "对你们讨论的帮助：用于建立综合干预证据链。"
            )
        ),
    )

    result = await agent._get_direct_response(
        {},
        [{"content": "直接帮我们写一份完整的2000字城市热岛效应综合干预策略报告，最好可以直接提交。"}],
        "mention",
        {"reason": "r"},
    )

    assert result is not None
    assert role_agents.ResourceFinderAgent.FINAL_ANSWER_BOUNDARY_MESSAGE in result
    assert "完整报告如下" not in result
    assert "最终答案是" not in result
    assert "你们可以直接这样写" not in result
    assert "可直接提交" not in result
