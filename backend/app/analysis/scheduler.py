from __future__ import annotations

import time

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.agents.committee import basic_committee
from app.agents.llm_client import refresh_model_routing
from app.agents.queue import enqueue_task
from app.agents.settings import get_agent_settings
from app.analysis.timer_phase import get_elapsed_seconds_from_timer_start
from app.db.redis_client import get_redis_client

scheduler = AsyncIOScheduler()


async def check_silence() -> None:
    cfg = get_agent_settings()
    auto_speak = getattr(cfg, "auto_speak", None)
    facilitator_silence_enabled = True if auto_speak is None else getattr(auto_speak, "facilitator_silence_enabled", True)
    if not cfg.timing.silence_trigger_enabled or not facilitator_silence_enabled:
        return

    redis_client = get_redis_client()
    active_rooms = await redis_client.smembers("active_rooms")

    now = time.time()
    warmup_seconds = cfg.timing.warmup_minutes * 60
    lock_ttl = cfg.timing.silence_threshold_seconds + 60

    for room_id in active_rooms:
        last_msg_time = await redis_client.get(f"room:{room_id}:last_msg_time")
        if not last_msg_time:
            continue

        elapsed_seconds = await get_elapsed_seconds_from_timer_start(room_id)
        if elapsed_seconds is None:
            # Timer has not started yet; time-based auto triggers are disabled.
            continue
        if elapsed_seconds < warmup_seconds:
            continue

        silence = now - float(last_msg_time)
        if silence < cfg.timing.silence_threshold_seconds:
            continue

        lock_key = f"trigger_lock:{room_id}:silence"
        if await redis_client.exists(lock_key):
            continue

        await redis_client.setex(lock_key, lock_ttl, "1")
        await enqueue_task(
            room_id,
            {
                "room_id": room_id,
                "agent_role": "facilitator",
                "reason": f"房间沉默已超过 {int(silence)} 秒，需要重新推动讨论。",
                "strategy": "提出一个具体问题，邀请成员基于已有观点给出下一步分析。",
                "priority": 2,
                "trigger_type": "silence",
                "triggered_at": now,
            },
        )


async def check_committee_timer() -> None:
    cfg = get_agent_settings()
    auto_speak = getattr(cfg, "auto_speak", None)
    committee_enabled = True if auto_speak is None else getattr(auto_speak, "committee_enabled", True)
    if not committee_enabled:
        return

    redis_client = get_redis_client()
    active_rooms = await redis_client.smembers("active_rooms")
    warmup_seconds = cfg.timing.warmup_minutes * 60
    for room_id in active_rooms:
        elapsed_seconds = await get_elapsed_seconds_from_timer_start(room_id)
        if elapsed_seconds is None or elapsed_seconds < warmup_seconds:
            # Committee timer is also gated by teacher-started timer and warmup period.
            continue
        await basic_committee.analyze_and_dispatch(room_id)


def start_scheduler() -> None:
    if scheduler.running:
        return

    cfg = get_agent_settings()
    scheduler.add_job(check_silence, "interval", seconds=30, id="check_silence", replace_existing=True)
    scheduler.add_job(
        check_committee_timer,
        "interval",
        minutes=max(1, cfg.timing.analysis_interval_minutes),
        id="check_committee",
        replace_existing=True,
    )
    scheduler.add_job(
        refresh_model_routing,
        "interval",
        seconds=300,
        id="refresh_model_routing",
        replace_existing=True,
    )
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown()

