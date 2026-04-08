from collections.abc import AsyncIterator
from urllib.parse import urlsplit, urlunsplit

import anthropic

from app.config import settings

try:
    from openai import AsyncOpenAI
except Exception:
    AsyncOpenAI = None

_anthropic_client: anthropic.AsyncAnthropic | None = None
_openai_client: AsyncOpenAI | None = None


def _provider() -> str:
    return (settings.LLM_PROVIDER or "openai_compatible").strip().lower()


def normalize_openai_base_url(base_url: str) -> str:
    """
    Normalize OpenAI-compatible base URLs for common relay misconfigurations.

    Fixes:
    - "https://host" -> "https://host/v1"
    - ".../v1/chat/completions" -> ".../v1"
    """
    raw = (base_url or "").strip()
    if not raw:
        return raw

    parts = urlsplit(raw)
    path = (parts.path or "").rstrip("/")

    if path.endswith("/chat/completions"):
        path = path[: -len("/chat/completions")]

    if path in {"", "/"}:
        path = "/v1"

    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def get_openai_client() -> AsyncOpenAI:
    global _openai_client
    if AsyncOpenAI is None:
        raise RuntimeError("openai package is not installed. Please install it in backend dependencies.")

    if _openai_client is None:
        # Compatibility strategy:
        # - If OPENAI_API_KEY is provided, use OPENAI_BASE_URL (or official default).
        # - Otherwise fall back to AI_API_KEY + AI_BASE_URL for relay providers.
        if settings.OPENAI_API_KEY:
            api_key = settings.OPENAI_API_KEY
            base_url = settings.OPENAI_BASE_URL or "https://api.openai.com/v1"
        else:
            api_key = settings.AI_API_KEY
            base_url = settings.AI_BASE_URL

        if not api_key:
            raise RuntimeError("OPENAI_API_KEY (or AI_API_KEY) is required for OpenAI-compatible calls.")
        if not base_url:
            raise RuntimeError("OPENAI_BASE_URL (or AI_BASE_URL) is required for OpenAI-compatible calls.")

        normalized_base_url = normalize_openai_base_url(base_url)
        _openai_client = AsyncOpenAI(api_key=api_key, base_url=normalized_base_url)
    return _openai_client


def get_claude_client() -> anthropic.AsyncAnthropic:
    global _anthropic_client
    if _anthropic_client is None:
        api_key = settings.ANTHROPIC_API_KEY or settings.AI_API_KEY or settings.OPENAI_API_KEY
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY (or AI_API_KEY/OPENAI_API_KEY) is required for Anthropic calls.")
        _anthropic_client = anthropic.AsyncAnthropic(
            api_key=api_key,
            base_url=settings.AI_BASE_URL,
        )
    return _anthropic_client


async def _stream_openai(
    system_prompt: str,
    messages: list[dict],
    model: str,
    max_tokens: int,
) -> AsyncIterator[str]:
    client = get_openai_client()

    req_messages = [{"role": "system", "content": system_prompt}, *messages]
    stream = await client.chat.completions.create(
        model=model,
        messages=req_messages,
        max_tokens=max_tokens,
        stream=True,
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta.content if chunk.choices else None
        if delta:
            yield delta


async def _stream_anthropic(
    system_prompt: str,
    messages: list[dict],
    model: str,
    max_tokens: int,
) -> AsyncIterator[str]:
    client = get_claude_client()
    async with client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=messages,
    ) as stream:
        async for text in stream.text_stream:
            yield text


async def stream_completion(
    system_prompt: str,
    messages: list[dict],
    model: str,
    max_tokens: int = 1024,
):
    provider = _provider()

    if provider in {"openai", "openai_compatible", "openai-compatible"}:
        async for token in _stream_openai(system_prompt, messages, model, max_tokens):
            yield token
        return

    async for token in _stream_anthropic(system_prompt, messages, model, max_tokens):
        yield token
