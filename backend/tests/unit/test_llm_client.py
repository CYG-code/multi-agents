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
