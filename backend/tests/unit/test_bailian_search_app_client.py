from __future__ import annotations

import json

import pytest

from app.agents.tools import bailian_search_app_client as client


class _FakeStreamResponse:
    def __init__(self, *, status_code: int = 200, lines: list[str] | None = None, text: str = ""):
        self.status_code = status_code
        self._lines = lines or []
        self.text = text

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def iter_lines(self):
        for line in self._lines:
            yield line

    def read(self):
        return None


class _FakeHttpxClient:
    def __init__(self, response: _FakeStreamResponse, recorder: dict | None = None):
        self._response = response
        self._recorder = recorder if recorder is not None else {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def stream(self, method, url, headers=None, json=None):
        self._recorder["method"] = method
        self._recorder["url"] = url
        self._recorder["headers"] = headers
        self._recorder["body"] = json
        return self._response


def _mk_chunk(text: str = "", extra_output: dict | None = None) -> str:
    output = {"session_id": "sid", "finish_reason": "null", "text": text}
    if extra_output:
        output.update(extra_output)
    obj = {"output": output, "usage": {"models": [{"model_id": "qwen-flash"}]}, "request_id": "rid-1"}
    return "data: " + json.dumps(obj, ensure_ascii=False)


def _install_fake_httpx(monkeypatch, response: _FakeStreamResponse, recorder: dict | None = None):
    def _factory(*_args, **_kwargs):
        return _FakeHttpxClient(response=response, recorder=recorder)

    monkeypatch.setattr(client.httpx, "Client", _factory)


@pytest.fixture
def _env(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test-123456")
    monkeypatch.setenv("BAILIAN_SEARCH_APP_ID", "app-test-1")
    monkeypatch.setenv("BAILIAN_SEARCH_APP_TIMEOUT_SECONDS", "90")

    class _Cfg:
        class _B:
            enabled = False
            app_id_env = "BAILIAN_SEARCH_APP_ID"
            timeout_seconds = 120

        bailian_search_app = _B()

    monkeypatch.setattr(client, "get_agent_settings", lambda: _Cfg())


def test_query_bailian_search_app_parses_sse_and_handles_initial_empty_text(monkeypatch, _env):
    lines = [
        _mk_chunk(""),
        _mk_chunk(""),
        _mk_chunk("第一段"),
        _mk_chunk("第二段"),
        "data: [DONE]",
    ]
    response = _FakeStreamResponse(status_code=200, lines=lines)
    _install_fake_httpx(monkeypatch, response)

    result = client.query_bailian_search_app("查询问题")

    assert result.raw_chunk_count == 4
    assert result.answer == "第一段第二段"
    assert result.warning == "No structured source fields found"


def test_query_bailian_search_app_records_agentrag_trace(monkeypatch, _env):
    lines = [
        _mk_chunk(
            "",
            extra_output={
                "thoughts": [
                    {"action_type": "agentRag", "action_name": "知识检索", "action": "rag", "observation": "obs"}
                ]
            },
        ),
        _mk_chunk("有内容"),
    ]
    response = _FakeStreamResponse(status_code=200, lines=lines)
    _install_fake_httpx(monkeypatch, response)

    result = client.query_bailian_search_app("查询问题")

    trace = "\n".join(result.tool_trace)
    assert "action_type" in trace
    assert "agentRag" in trace
    assert "知识检索" in trace
    assert "observation" in trace


def test_query_bailian_search_app_with_structured_sources_sets_flag(monkeypatch, _env):
    lines = [
        _mk_chunk("", extra_output={"title": "资料标题", "url": "https://example.com", "source": "学报"}),
        _mk_chunk("有内容"),
    ]
    response = _FakeStreamResponse(status_code=200, lines=lines)
    _install_fake_httpx(monkeypatch, response)

    result = client.query_bailian_search_app("查询问题")
    assert result.has_structured_sources is True
    assert result.warning is None


def test_query_bailian_search_app_empty_answer_returns_warning(monkeypatch, _env):
    lines = [_mk_chunk(""), _mk_chunk(""), "data: [DONE]"]
    response = _FakeStreamResponse(status_code=200, lines=lines)
    _install_fake_httpx(monkeypatch, response)

    result = client.query_bailian_search_app("查询问题")
    assert result.answer == ""
    assert result.warning == "Answer is empty from Bailian search app"


def test_query_bailian_search_app_http_non_200_raises(monkeypatch, _env):
    response = _FakeStreamResponse(status_code=403, lines=[], text='{"code":"AccessDenied"}')
    _install_fake_httpx(monkeypatch, response)

    with pytest.raises(client.BailianSearchAppError) as e:
        client.query_bailian_search_app("查询问题")
    assert "HTTP 403" in str(e.value)
    assert "sk-test-123456" not in str(e.value)


def test_query_bailian_search_app_missing_api_key_raises(monkeypatch, _env):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.setattr(client.settings, "DASHSCOPE_API_KEY", "")
    response = _FakeStreamResponse(status_code=200, lines=[])
    _install_fake_httpx(monkeypatch, response)

    with pytest.raises(client.BailianSearchAppError) as e:
        client.query_bailian_search_app("查询问题")
    assert "Missing DASHSCOPE_API_KEY" in str(e.value)


def test_query_bailian_search_app_missing_app_id_raises(monkeypatch, _env):
    monkeypatch.delenv("BAILIAN_SEARCH_APP_ID", raising=False)
    monkeypatch.setattr(client.settings, "BAILIAN_SEARCH_APP_ID", "")
    response = _FakeStreamResponse(status_code=200, lines=[])
    _install_fake_httpx(monkeypatch, response)

    with pytest.raises(client.BailianSearchAppError) as e:
        client.query_bailian_search_app("查询问题")
    assert "Missing BAILIAN_SEARCH_APP_ID" in str(e.value)


def test_query_bailian_search_app_sends_expected_request_body(monkeypatch, _env):
    recorder = {}
    lines = [_mk_chunk("ok")]
    response = _FakeStreamResponse(status_code=200, lines=lines)
    _install_fake_httpx(monkeypatch, response, recorder)

    client.query_bailian_search_app("测试查询")

    assert recorder["method"] == "POST"
    assert "/api/v1/apps/app-test-1/completion" in recorder["url"]
    assert recorder["body"]["input"]["prompt"] == "测试查询"
    assert recorder["body"]["parameters"]["incremental_output"] is True
    assert recorder["body"]["parameters"]["has_thoughts"] is True


def test_query_bailian_search_app_uses_settings_when_env_missing(monkeypatch, _env):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("BAILIAN_SEARCH_APP_ID", raising=False)
    monkeypatch.delenv("BAILIAN_SEARCH_APP_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setattr(client.settings, "DASHSCOPE_API_KEY", "sk-settings-9999")
    monkeypatch.setattr(client.settings, "BAILIAN_SEARCH_APP_ID", "app-settings-2")
    monkeypatch.setattr(client.settings, "BAILIAN_SEARCH_APP_TIMEOUT_SECONDS", 77)

    recorder = {}
    lines = [_mk_chunk("ok")]
    response = _FakeStreamResponse(status_code=200, lines=lines)
    _install_fake_httpx(monkeypatch, response, recorder)

    result = client.query_bailian_search_app("query")
    assert result.answer == "ok"
    assert "/api/v1/apps/app-settings-2/completion" in recorder["url"]


def test_is_bailian_search_app_enabled_env_override(monkeypatch, _env):
    monkeypatch.setenv("BAILIAN_SEARCH_APP_ENABLED", "1")
    assert client.is_bailian_search_app_enabled() is True

    monkeypatch.setenv("BAILIAN_SEARCH_APP_ENABLED", "0")
    assert client.is_bailian_search_app_enabled() is False
