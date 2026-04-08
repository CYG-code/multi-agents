import os

import pytest

from app.config import settings
from app.agents.llm_client import stream_completion


def _is_enabled() -> bool:
    value = os.getenv("RUN_RELAY_API_TEST", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


@pytest.mark.asyncio
async def test_relay_api_connectivity_and_generation():
    """
    Targeted integration test for relay API connectivity and AI generation.

    This test is intentionally opt-in to avoid hitting external services in CI.

    Run example (PowerShell):
      $env:RUN_RELAY_API_TEST='1'
      python -m pytest tests/integration/test_relay_api_connection.py -q
    """
    if not _is_enabled():
        pytest.skip("Set RUN_RELAY_API_TEST=1 to enable external relay API test.")

    api_key = settings.OPENAI_API_KEY or settings.AI_API_KEY or settings.ANTHROPIC_API_KEY
    assert api_key, "No API key configured (OPENAI_API_KEY/AI_API_KEY/ANTHROPIC_API_KEY)."
    assert settings.AGENT_MODEL, "AGENT_MODEL is empty."

    if settings.LLM_PROVIDER.strip().lower() in {"openai", "openai_compatible", "openai-compatible"}:
        base_url = settings.OPENAI_BASE_URL if settings.OPENAI_API_KEY else settings.AI_BASE_URL
        assert base_url, "OpenAI-compatible provider requires OPENAI_BASE_URL or AI_BASE_URL."

    tokens: list[str] = []
    async for token in stream_completion(
        system_prompt="You are a concise assistant.",
        messages=[{"role": "user", "content": "Please reply with one short hello sentence."}],
        model=settings.AGENT_MODEL,
        max_tokens=64,
    ):
        if token:
            tokens.append(token)
        if len(tokens) >= 3:
            break

    joined = "".join(tokens).strip()
    assert tokens, (
        "Relay API call finished without any stream tokens. "
        "Check base URL path (often needs /v1), provider setting, and API key validity."
    )
    assert joined, "Received stream events but token content is empty."
