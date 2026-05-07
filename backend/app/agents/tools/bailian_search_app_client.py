from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.agents.settings import get_agent_settings
from app.config import settings

_SOURCE_KEYS = {
    "citation",
    "citations",
    "reference",
    "references",
    "source",
    "sources",
    "url",
    "title",
    "doc_references",
}
_TRACE_KEYS = {"action_type", "action_name", "action", "thoughts", "observation"}


class BailianSearchAppError(RuntimeError):
    pass


@dataclass
class BailianSearchAppResult:
    answer: str
    source_names: list[str] = field(default_factory=list)
    has_structured_sources: bool = False
    tool_trace: list[str] = field(default_factory=list)
    warning: str | None = None
    raw_chunk_count: int = 0


def _decode_line(line: Any) -> str:
    if isinstance(line, bytes):
        return line.decode("utf-8", errors="replace").strip()
    return str(line).strip()


def _scan_paths(obj: Any, path: str = "", out: list[tuple[str, Any]] | None = None) -> list[tuple[str, Any]]:
    if out is None:
        out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            out.append((p, v))
            _scan_paths(v, p, out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            p = f"{path}[{i}]"
            out.append((p, v))
            _scan_paths(v, p, out)
    return out


def _extract_output_text(chunk: dict[str, Any]) -> str:
    output = chunk.get("output", {})
    if isinstance(output, dict):
        txt = output.get("text")
        if isinstance(txt, str):
            return txt
    return ""


def _extract_source_names_from_answer(answer: str) -> list[str]:
    lines = [ln.strip() for ln in str(answer or "").splitlines()]
    out: list[str] = []
    for line in lines:
        if line.startswith("来源："):
            value = line.split("：", 1)[1].strip()
            if value and value not in out:
                out.append(value)
        elif line.lower().startswith("来源:"):
            value = line.split(":", 1)[1].strip()
            if value and value not in out:
                out.append(value)
    return out


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def is_bailian_search_app_enabled() -> bool:
    env_enabled = os.getenv("BAILIAN_SEARCH_APP_ENABLED")
    if env_enabled is not None and str(env_enabled).strip() != "":
        return _truthy(env_enabled)
    cfg = get_agent_settings()
    return bool(cfg.bailian_search_app.enabled)


def _resolve_api_key() -> str:
    env_key = (os.getenv("DASHSCOPE_API_KEY") or "").strip()
    if env_key:
        return env_key
    settings_key = (getattr(settings, "DASHSCOPE_API_KEY", "") or "").strip()
    if settings_key:
        return settings_key
    raise BailianSearchAppError("Missing DASHSCOPE_API_KEY")


def _resolve_app_id(app_id_env: str) -> str:
    env_app_id = (os.getenv(app_id_env) or "").strip()
    if env_app_id:
        return env_app_id
    settings_app_id = (getattr(settings, "BAILIAN_SEARCH_APP_ID", "") or "").strip()
    if settings_app_id:
        return settings_app_id
    raise BailianSearchAppError(f"Missing {app_id_env}")


def _resolve_timeout(default_timeout_seconds: int) -> int:
    env_timeout = os.getenv("BAILIAN_SEARCH_APP_TIMEOUT_SECONDS")
    if env_timeout and env_timeout.isdigit():
        return max(5, int(env_timeout))
    settings_timeout = getattr(settings, "BAILIAN_SEARCH_APP_TIMEOUT_SECONDS", 0)
    if isinstance(settings_timeout, int) and settings_timeout > 0:
        return max(5, settings_timeout)
    return max(5, int(default_timeout_seconds))


def query_bailian_search_app(query: str) -> BailianSearchAppResult:
    cfg = get_agent_settings()
    app_cfg = cfg.bailian_search_app

    api_key = _resolve_api_key()

    app_id_env = (app_cfg.app_id_env or "BAILIAN_SEARCH_APP_ID").strip()
    app_id = _resolve_app_id(app_id_env)
    timeout_seconds = _resolve_timeout(int(app_cfg.timeout_seconds))

    url = f"https://dashscope.aliyuncs.com/api/v1/apps/{app_id}/completion"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-DashScope-SSE": "enable",
    }
    body = {
        "input": {"prompt": query},
        "parameters": {"incremental_output": True, "has_thoughts": True},
    }

    chunks: list[dict[str, Any]] = []
    output_parts: list[str] = []
    structured_source_found = False
    tool_trace: list[str] = []
    warning: str | None = None

    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            with client.stream("POST", url, headers=headers, json=body) as response:
                if response.status_code != 200:
                    snippet = ""
                    try:
                        response.read()
                        snippet = (response.text or "")[:300]
                    except Exception:
                        snippet = ""
                    raise BailianSearchAppError(
                        f"Bailian search app HTTP {response.status_code}"
                        + (f": {snippet}" if snippet else "")
                    )

                for line in response.iter_lines():
                    s = _decode_line(line)
                    if not s.startswith("data:"):
                        continue
                    payload = s[len("data:") :].strip()
                    if payload == "[DONE]":
                        continue
                    try:
                        obj = json.loads(payload)
                    except json.JSONDecodeError as exc:
                        raise BailianSearchAppError(f"SSE JSON parse failed: {exc}") from exc

                    chunks.append(obj)
                    txt = _extract_output_text(obj)
                    if txt.strip():
                        output_parts.append(txt)

                    for path, value in _scan_paths(obj):
                        key_name = path.split(".")[-1].lower()
                        if key_name in _SOURCE_KEYS and value not in (None, "", [], {}):
                            structured_source_found = True
                        if key_name in _TRACE_KEYS:
                            trace_line = f"{path}={value}" if isinstance(value, str) else f"{path}"
                            if trace_line not in tool_trace:
                                tool_trace.append(trace_line[:300])
    except httpx.TimeoutException as exc:
        raise BailianSearchAppError(f"Bailian search app timeout after {timeout_seconds}s") from exc
    except httpx.HTTPError as exc:
        raise BailianSearchAppError(f"Bailian search app request failed: {exc.__class__.__name__}") from exc

    if not chunks:
        raise BailianSearchAppError("No SSE chunks received from Bailian search app")

    joined = "".join(output_parts).strip()
    longest = max(output_parts, key=len) if output_parts else ""
    final_answer = longest if len(longest) > len(joined) else joined

    if not final_answer:
        warning = "Answer is empty from Bailian search app"
    elif not structured_source_found:
        warning = "No structured source fields found"

    return BailianSearchAppResult(
        answer=final_answer,
        source_names=_extract_source_names_from_answer(final_answer),
        has_structured_sources=structured_source_found,
        tool_trace=tool_trace,
        warning=warning,
        raw_chunk_count=len(chunks),
    )

