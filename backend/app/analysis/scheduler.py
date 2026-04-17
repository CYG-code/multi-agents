import asyncio
import time
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
import yaml

from app.agents.context_builder import get_recent_messages, get_room_context
from app.agents.llm_client import refresh_model_routing
from app.agents.role_agents import FacilitatorAgent
from app.db.redis_client import get_redis_client

scheduler = AsyncIOScheduler()
facilitator = FacilitatorAgent()

DEFAULT_SILENCE_TRIGGER_ENABLED = True
DEFAULT_SILENCE_THRESHOLD_SECONDS = 180
DEFAULT_WARMUP_MINUTES = 2

_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "agents" / "agent_settings.yaml"


def _to_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes", "on", "enabled"}:
        return True
    if lowered in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


def _load_timing_config() -> tuple[bool, int, int]:
    try:
        raw = yaml.safe_load(_SETTINGS_PATH.read_text(encoding="utf-8")) or {}
        timing = raw.get("timing", {})

        silence_enabled = _to_bool(
            timing.get("silence_trigger_enabled", DEFAULT_SILENCE_TRIGGER_ENABLED),
            DEFAULT_SILENCE_TRIGGER_ENABLED,
        )

        silence_threshold = int(timing.get("silence_threshold_seconds", DEFAULT_SILENCE_THRESHOLD_SECONDS))
        warmup_minutes = int(timing.get("warmup_minutes", DEFAULT_WARMUP_MINUTES))

        if silence_threshold <= 0:
            silence_threshold = DEFAULT_SILENCE_THRESHOLD_SECONDS
        if warmup_minutes < 0:
            warmup_minutes = DEFAULT_WARMUP_MINUTES

        return silence_enabled, silence_threshold, warmup_minutes
    except Exception:
        return DEFAULT_SILENCE_TRIGGER_ENABLED, DEFAULT_SILENCE_THRESHOLD_SECONDS, DEFAULT_WARMUP_MINUTES


def _normalize_room_id(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


async def check_silence():
    silence_enabled, silence_threshold_seconds, warmup_minutes = _load_timing_config()
    if not silence_enabled:
        return

    warmup_seconds = warmup_minutes * 60
    trigger_lock_ttl_seconds = silence_threshold_seconds + 60

    redis_client = get_redis_client()
    active_rooms_raw = await redis_client.smembers("active_rooms")
    active_rooms = [_normalize_room_id(room_id) for room_id in active_rooms_raw]

    now = time.time()
    for room_id in active_rooms:
        last_msg_time = await redis_client.get(f"room:{room_id}:last_msg_time")
        if not last_msg_time:
            continue

        room_start_time = await redis_client.get(f"room:{room_id}:start_time")
        if room_start_time and (now - float(room_start_time) < warmup_seconds):
            continue

        silence_duration = now - float(last_msg_time)
        if silence_duration >= silence_threshold_seconds:
            lock_key = f"trigger_lock:{room_id}:silence"
            if not await redis_client.exists(lock_key):
                # Lock at least one silence cycle to avoid repeated trigger loops.
                await redis_client.setex(lock_key, trigger_lock_ttl_seconds, "1")
                context = await get_room_context(room_id)
                history = await get_recent_messages(room_id)
                asyncio.create_task(
                    facilitator.generate_and_push(
                        room_id,
                        context,
                        history,
                        source_message_id=None,
                        trigger_type="silence",
                    )
                )


def start_scheduler():
    if scheduler.running:
        return
    scheduler.add_job(check_silence, "interval", seconds=30)
    scheduler.add_job(refresh_model_routing, "interval", seconds=300)
    scheduler.start()


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
