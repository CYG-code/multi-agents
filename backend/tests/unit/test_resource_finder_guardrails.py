from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agents import role_agents
from app.agents.tools.bailian_search_app_client import BailianSearchAppError, BailianSearchAppResult


def _fake_settings(enabled: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        bailian_search_app=SimpleNamespace(enabled=enabled, app_id_env="BAILIAN_SEARCH_APP_ID")
    )


@pytest.mark.asyncio
async def test_resource_finder_disabled_does_not_call_bailian(monkeypatch):
    agent = role_agents.ResourceFinderAgent()
    called = {"value": False}

    def _fake_query(_query: str):
        called["value"] = True
        return BailianSearchAppResult(answer="x")

    monkeypatch.setattr(role_agents, "get_agent_settings", lambda: _fake_settings(enabled=False))
    monkeypatch.setattr(role_agents, "query_bailian_search_app", _fake_query)
    monkeypatch.setenv("BAILIAN_SEARCH_APP_ID", "app-id")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")

    result = await agent._get_direct_response({}, [{"content": "给我资料"}], "mention", {"reason": "r"})
    assert result is None
    assert called["value"] is False


@pytest.mark.asyncio
async def test_resource_finder_normal_scaffold_output(monkeypatch):
    agent = role_agents.ResourceFinderAgent()

    monkeypatch.setattr(role_agents, "get_agent_settings", lambda: _fake_settings(enabled=True))
    monkeypatch.setenv("BAILIAN_SEARCH_APP_ID", "app-id")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    monkeypatch.setattr(
        role_agents,
        "query_bailian_search_app",
        lambda _q: BailianSearchAppResult(
            answer=(
                "1. 资料名称：城市热岛与地表温度\n"
                "来源：某城市生态研究中心\n"
                "主要内容：分析地表温度与绿化率关系。\n"
                "对你们讨论的帮助：可用于解释热岛成因。"
            ),
            has_structured_sources=False,
        ),
    )

    result = await agent._get_direct_response(
        {},
        [{"content": "请帮我找城市热岛相关资料"}],
        "mention",
        {"reason": "r"},
    )
    assert result is not None
    assert "资料名称" in result
    assert "来源" in result
    assert "对你们讨论的帮助" in result


@pytest.mark.asyncio
async def test_resource_finder_final_answer_request_guardrail(monkeypatch):
    agent = role_agents.ResourceFinderAgent()

    monkeypatch.setattr(role_agents, "get_agent_settings", lambda: _fake_settings(enabled=True))
    monkeypatch.setenv("BAILIAN_SEARCH_APP_ID", "app-id")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    monkeypatch.setattr(
        role_agents,
        "query_bailian_search_app",
        lambda _q: BailianSearchAppResult(
            answer="1. 资料名称：热岛治理政策\n来源：某规划院\n主要内容：干预措施综述。\n对你们讨论的帮助：可作为措施依据。"
        ),
    )

    result = await agent._get_direct_response(
        {},
        [{"content": "直接帮我们写完整报告"}],
        "mention",
        {"reason": "r"},
    )
    assert "我不能直接替你们生成最终报告或标准答案" in (result or "")
    assert "完整报告如下" not in (result or "")
    assert "最终答案是" not in (result or "")


@pytest.mark.asyncio
async def test_resource_finder_empty_answer_fallback(monkeypatch):
    agent = role_agents.ResourceFinderAgent()

    monkeypatch.setattr(role_agents, "get_agent_settings", lambda: _fake_settings(enabled=True))
    monkeypatch.setenv("BAILIAN_SEARCH_APP_ID", "app-id")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    monkeypatch.setattr(role_agents, "query_bailian_search_app", lambda _q: BailianSearchAppResult(answer=""))

    result = await agent._get_direct_response({}, [{"content": "给资料"}], "mention", {"reason": "r"})
    assert "当前无法获取可靠的外部资料" in (result or "")


@pytest.mark.asyncio
async def test_resource_finder_client_error_fallback(monkeypatch):
    agent = role_agents.ResourceFinderAgent()

    monkeypatch.setattr(role_agents, "get_agent_settings", lambda: _fake_settings(enabled=True))
    monkeypatch.setenv("BAILIAN_SEARCH_APP_ID", "app-id")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")

    def _raise(_q: str):
        raise BailianSearchAppError("boom")

    monkeypatch.setattr(role_agents, "query_bailian_search_app", _raise)

    result = await agent._get_direct_response({}, [{"content": "给资料"}], "mention", {"reason": "r"})
    assert "当前无法获取可靠的外部资料" in (result or "")
    assert "boom" not in (result or "")
    assert "sk-test" not in (result or "")


@pytest.mark.asyncio
async def test_resource_finder_dangerous_output_sanitized(monkeypatch):
    agent = role_agents.ResourceFinderAgent()

    monkeypatch.setattr(role_agents, "get_agent_settings", lambda: _fake_settings(enabled=True))
    monkeypatch.setenv("BAILIAN_SEARCH_APP_ID", "app-id")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    monkeypatch.setattr(
        role_agents,
        "query_bailian_search_app",
        lambda _q: BailianSearchAppResult(
            answer="完整报告如下：你们可以直接这样写，最终答案是……城市热岛问题……"
        ),
    )

    result = await agent._get_direct_response({}, [{"content": "给资料"}], "mention", {"reason": "r"})
    assert "完整报告如下" not in (result or "")
    assert "最终答案是" not in (result or "")
    assert "你们可以直接这样写" not in (result or "")
    assert "当前无法获取可靠的外部资料" in (result or "")


@pytest.mark.asyncio
async def test_resource_finder_accepts_no_structured_sources(monkeypatch):
    agent = role_agents.ResourceFinderAgent()

    monkeypatch.setattr(role_agents, "get_agent_settings", lambda: _fake_settings(enabled=True))
    monkeypatch.setenv("BAILIAN_SEARCH_APP_ID", "app-id")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    monkeypatch.setattr(
        role_agents,
        "query_bailian_search_app",
        lambda _q: BailianSearchAppResult(
            answer=(
                "资料名称：城市热岛成因综述\n"
                "来源：中国城市气候研究会\n"
                "主要内容：地表温度、人流密度、绿化率与热岛强度关系。\n"
                "对你们讨论的帮助：可用于解释机制并支持干预方向。"
            ),
            has_structured_sources=False,
            warning="No structured source fields found",
        ),
    )

    result = await agent._get_direct_response({}, [{"content": "请给资料"}], "mention", {"reason": "r"})
    assert result is not None
    assert "来源：中国城市气候研究会" in result
