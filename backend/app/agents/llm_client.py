import anthropic

from app.config import settings

_client: anthropic.AsyncAnthropic | None = None


def get_claude_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        api_key = settings.AI_API_KEY or settings.ANTHROPIC_API_KEY
        if not api_key:
            raise RuntimeError("AI_API_KEY or ANTHROPIC_API_KEY is required for Claude calls.")
        _client = anthropic.AsyncAnthropic(
            api_key=api_key,
            base_url=settings.AI_BASE_URL,
        )
    return _client


async def stream_completion(
    system_prompt: str,
    messages: list[dict],
    model: str,
    max_tokens: int = 1024,
):
    client = get_claude_client()
    async with client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=messages,
    ) as stream:
        async for text in stream.text_stream:
            yield text
