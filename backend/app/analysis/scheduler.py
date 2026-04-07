import asyncio
import time
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
import yaml

from app.agents.context_builder import get_recent_messages, get_room_context
from app.agents.role_agents import FacilitatorAgent
from app.db.redis_client import get_redis_client

scheduler = AsyncIOScheduler()
facilitator = FacilitatorAgent()

DEFAULT_SILENCE_THRESHOLD_SECONDS = 180


def _load_silence_threshold_seconds() -> int:
    config_path = Path(__file__).resolve().parent.parent / "agents" / "agent_settings.yaml"
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        value = raw.get("timing", {}).get("silence_threshold_seconds", DEFAULT_SILENCE_THRESHOLD_SECONDS)
        threshold = int(value)
        return threshold if threshold > 0 else DEFAULT_SILENCE_THRESHOLD_SECONDS
    except Exception:
        return DEFAULT_SILENCE_THRESHOLD_SECONDS


SILENCE_THRESHOLD_SECONDS = _load_silence_threshold_seconds()
TRIGGER_LOCK_TTL_SECONDS = SILENCE_THRESHOLD_SECONDS + 60


def _normalize_room_id(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


async def check_silence():
    redis_client = get_redis_client()
    active_rooms_raw = await redis_client.smembers("active_rooms")
    active_rooms = [_normalize_room_id(room_id) for room_id in active_rooms_raw]

    now = time.time()
    for room_id in active_rooms:
        last_msg_time = await redis_client.get(f"room:{room_id}:last_msg_time")
        if not last_msg_time:
            continue

        silence_duration = now - float(last_msg_time)
        if silence_duration >= SILENCE_THRESHOLD_SECONDS:
            lock_key = f"trigger_lock:{room_id}:silence"
            if not await redis_client.exists(lock_key):
                # Lock at least one silence cycle to avoid repeated trigger loops.
                await redis_client.setex(lock_key, TRIGGER_LOCK_TTL_SECONDS, "1")
                context = await get_room_context(room_id)
                history = await get_recent_messages(room_id)
                asyncio.create_task(facilitator.generate_and_push(room_id, context, history))


def start_scheduler():
    if scheduler.running:
        return
    scheduler.add_job(check_silence, "interval", seconds=30)
    scheduler.start()


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
