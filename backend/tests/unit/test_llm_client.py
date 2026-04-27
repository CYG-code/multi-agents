import pytest

from app.agents import llm_client
from app.agents.model_pool import MODEL_CANDIDATES
from app.agents.llm_client import normalize_openai_base_url


def test_normalize_openai_base_url_adds_v1_for_host_root():
    assert normalize_openai_base_url("https://yunwu.ai") == "https://yunwu.ai/v1"
    assert normalize_openai_base_url("https://yunwu.ai/") == "https://yunwu.ai/v1"


def test_normalize_openai_base_url_strips_chat_completions_path():
    assert (
        normalize_openai_base_url("https://yunwu.ai/v1/chat/completions")
        == "https://yunwu.ai/v1"
    )


def test_normalize_openai_base_url_keeps_valid_v1_path():
    assert normalize_openai_base_url("https://api.openai.com/v1") == "https://api.openai.com/v1"


def test_model_candidates_are_fixed_pool():
    assert llm_client.get_model_candidates() == MODEL_CANDIDATES


@pytest.mark.asyncio
async def test_stream_completion_uses_openai_branch(monkeypatch):
    monkeypatch.setattr(llm_client, "_provider", lambda: "openai_compatible")

    async def _fake_stream_openai(_system_prompt, _messages, _model, _max_tokens):
        yield "A"
        yield "B"

    monkeypatch.setattr(llm_client, "_stream_openai", _fake_stream_openai)

    tokens = []
    async for token in llm_client.stream_completion("sys", [{"role": "user", "content": "hi"}], "m"):
        tokens.append(token)

    assert tokens == ["A", "B"]


@pytest.mark.asyncio
async def test_stream_completion_openai_fallback_on_retryable_error(monkeypatch):
    monkeypatch.setattr(llm_client, "_provider", lambda: "openai_compatible")

    async def _fake_candidates(_preferred):
        return ["m1", "m2"]

    calls = []

    async def _fake_stream_openai(_system_prompt, _messages, model, _max_tokens):
        calls.append(model)
        if model == "m1":
            raise RuntimeError("Connection error.")
        yield "OK"

    async def _fake_mark_success(_model, _reason):
        return None

    async def _fake_mark_failure(_model, _exc, cooldown):
        return None

    monkeypatch.setattr(llm_client, "_ordered_candidates", _fake_candidates)
    monkeypatch.setattr(llm_client, "_stream_openai", _fake_stream_openai)
    monkeypatch.setattr(llm_client, "_mark_success", _fake_mark_success)
    monkeypatch.setattr(llm_client, "_mark_failure", _fake_mark_failure)
    monkeypatch.setattr(llm_client, "_is_retryable_error", lambda _exc: True)

    tokens = []
    async for token in llm_client.stream_completion("sys", [{"role": "user", "content": "hi"}], "m"):
        tokens.append(token)

    assert tokens == ["OK"]
    assert calls == ["m1", "m2"]


@pytest.mark.asyncio
async def test_stream_completion_uses_anthropic_branch(monkeypatch):
    monkeypatch.setattr(llm_client, "_provider", lambda: "anthropic")

    async def _fake_stream_anthropic(_system_prompt, _messages, _model, _max_tokens):
        yield "X"

    monkeypatch.setattr(llm_client, "_stream_anthropic", _fake_stream_anthropic)

    tokens = []
    async for token in llm_client.stream_completion("sys", [{"role": "user", "content": "hi"}], "m"):
        tokens.append(token)

    assert tokens == ["X"]


@pytest.mark.asyncio
async def test_stream_openai_propagates_client_errors(monkeypatch):
    class _FailingCompletions:
        async def create(self, **_kwargs):
            raise RuntimeError("connection down")

    class _FailingChat:
        completions = _FailingCompletions()

    class _FailingClient:
        chat = _FailingChat()

    monkeypatch.setattr(llm_client, "get_openai_client", lambda: _FailingClient())

    with pytest.raises(RuntimeError, match="connection down"):
        async for _ in llm_client._stream_openai("sys", [{"role": "user", "content": "hello"}], "m", 64):
            pass

