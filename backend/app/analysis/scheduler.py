from __future__ import annotations

import time
from datetime import timezone
from uuid import UUID

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.agents.committee import basic_committee
from app.agents.llm_client import refresh_model_routing
from app.agents.queue import enqueue_task
from app.agents.settings import get_agent_settings
from app.analysis.timer_phase import get_elapsed_seconds_from_timer_start
from app.db.redis_client import cleanup_stale_online_presence, get_redis_client
from app.db.session import AsyncSessionLocal
from app.models.room import Room
from app.models.task import Task
from app.services import writing_submit_service

scheduler = AsyncIOScheduler()
TIME_NODE_MINUTES = (15, 35, 55, 75, 88)
TIME_NODE_LOCK_TTL_SECONDS = 4 * 3600


def _decode_room_id(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return str(value or "").strip()


def _normalize_script_value(raw_scripts) -> dict:
    if not isinstance(raw_scripts, dict):
        return {"current_status": "", "next_goal": "", "history": [], "pending_proposal": None}
    history = raw_scripts.get("history")
    pending = raw_scripts.get("pending_proposal")
    return {
        "current_status": str(raw_scripts.get("current_status") or "").strip(),
        "next_goal": str(raw_scripts.get("next_goal") or "").strip(),
        "history": history if isinstance(history, list) else [],
        "pending_proposal": pending if isinstance(pending, dict) else None,
    }


def _is_meaningful_text(text: str) -> bool:
    normalized = (text or "").strip().lower()
    if not normalized:
        return False
    return normalized not in {"none", "null", "n/a", "-", "无", "暂无", "暂无。", "暂时无"}


def _phase_label(elapsed_minutes: int) -> str:
    if elapsed_minutes < 30:
        return "early"
    if elapsed_minutes < 70:
        return "middle"
    return "late"


def _assess_progress(
    *,
    phase: str,
    script_state: dict,
    submit_confirm_count: int,
    has_recent_activity: bool,
) -> tuple[str, str]:
    history_count = len(script_state.get("history") or [])
    has_pending = bool(script_state.get("pending_proposal"))
    has_current_status = _is_meaningful_text(script_state.get("current_status") or "")
    has_next_goal = _is_meaningful_text(script_state.get("next_goal") or "")

    if phase == "early":
        is_normal = has_next_goal or has_pending or history_count >= 1
    elif phase == "middle":
        is_normal = (history_count >= 1 or has_pending) and has_current_status and has_next_goal and has_recent_activity
    else:
        is_normal = submit_confirm_count >= 1 or ((history_count >= 2 or has_pending) and has_next_goal and has_recent_activity)

    status = "normal" if is_normal else "slow"
    details = (
        f"phase={phase}, history_count={history_count}, has_pending={has_pending}, "
        f"has_current_status={has_current_status}, has_next_goal={has_next_goal}, "
        f"submit_confirm_count={submit_confirm_count}, recent_activity={has_recent_activity}"
    )
    return status, details


def _build_time_nudge_text(
    *,
    elapsed_minutes: int,
    node_minutes: int,
    phase: str,
    progress_status: str,
    progress_details: str,
) -> tuple[str, str]:
    phase_text = {"early": "前期", "middle": "中期", "late": "后期"}.get(phase, "当前阶段")
    progress_text = "进度正常" if progress_status == "normal" else "进度偏慢"
    reason = (
        f"时间节点提醒：已进行 {elapsed_minutes} 分钟（命中 {node_minutes} 分钟节点），"
        f"当前处于{phase_text}，判断为{progress_text}。"
    )
    if progress_status == "slow":
        strategy = (
            f"请用 5-8 分钟明确分工并收敛：先确认当前状态，再确定下一步目标，最后指定每位同学的短任务。"
            f"诊断信息：{progress_details}"
        )
    else:
        strategy = (
            f"请继续保持节奏并做一次小结：确认当前状态是否清晰、下一步目标是否可执行，必要时提前安排收敛动作。"
            f"诊断信息：{progress_details}"
        )
    return reason, strategy


async def _load_room_snapshot(room_id: str) -> dict | None:
    try:
        parsed_room_id = UUID(room_id)
    except (ValueError, TypeError):
        return None

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(
                Room.timer_started_at,
                Room.timer_stopped_at,
                Task.scripts.label("task_scripts"),
            )
            .outerjoin(Task, Task.id == Room.task_id)
            .where(Room.id == parsed_room_id)
        )
        row = result.first()

    if row is None:
        return None

    timer_started_at = row.timer_started_at
    timer_stopped_at = row.timer_stopped_at
    if timer_started_at is None or timer_stopped_at is not None:
        return None
    if timer_started_at.tzinfo is None:
        timer_started_at = timer_started_at.replace(tzinfo=timezone.utc)

    return {
        "timer_started_at": timer_started_at,
        "script_state": _normalize_script_value(row.task_scripts),
    }


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
        last_activity_time = await redis_client.get(f"room:{room_id}:last_activity_time")
        if not last_activity_time:
            # Backward compatibility: older rooms may only have chat timestamp.
            last_activity_time = await redis_client.get(f"room:{room_id}:last_msg_time")
        if not last_activity_time:
            continue

        elapsed_seconds = await get_elapsed_seconds_from_timer_start(room_id)
        if elapsed_seconds is None:
            # Timer has not started yet; time-based auto triggers are disabled.
            continue
        if elapsed_seconds < warmup_seconds:
            continue

        silence = now - float(last_activity_time)
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


async def check_time_progress_reminders() -> None:
    cfg = get_agent_settings()
    auto_speak = getattr(cfg, "auto_speak", None)
    facilitator_silence_enabled = True if auto_speak is None else getattr(auto_speak, "facilitator_silence_enabled", True)
    if not facilitator_silence_enabled:
        return

    redis_client = get_redis_client()
    active_rooms = await redis_client.smembers("active_rooms")
    now = time.time()

    for raw_room_id in active_rooms:
        room_id = _decode_room_id(raw_room_id)
        if not room_id:
            continue

        elapsed_seconds = await get_elapsed_seconds_from_timer_start(room_id)
        if elapsed_seconds is None:
            continue

        elapsed_minutes = int(elapsed_seconds // 60)
        matched_node = next((n for n in TIME_NODE_MINUTES if elapsed_minutes >= n), None)
        if matched_node is None:
            continue

        # We only emit the newest node each run; older nodes are naturally skipped.
        for node in reversed(TIME_NODE_MINUTES):
            if elapsed_minutes >= node:
                matched_node = node
                break

        snapshot = await _load_room_snapshot(room_id)
        if snapshot is None:
            continue
        cycle_id = int(snapshot["timer_started_at"].timestamp())
        lock_key = f"trigger_lock:{room_id}:time_progress:{cycle_id}:{matched_node}"
        if await redis_client.exists(lock_key):
            continue

        last_activity_time = await redis_client.get(f"room:{room_id}:last_activity_time")
        if not last_activity_time:
            last_activity_time = await redis_client.get(f"room:{room_id}:last_msg_time")
        has_recent_activity = False
        if last_activity_time:
            try:
                has_recent_activity = (now - float(last_activity_time)) <= 300
            except (TypeError, ValueError):
                has_recent_activity = False

        submit_state = await writing_submit_service.get_writing_submit_state(room_id)
        submit_confirm_count = len(submit_state.get("confirmations") or [])
        phase = _phase_label(elapsed_minutes)
        progress_status, progress_details = _assess_progress(
            phase=phase,
            script_state=snapshot["script_state"],
            submit_confirm_count=submit_confirm_count,
            has_recent_activity=has_recent_activity,
        )
        reason, strategy = _build_time_nudge_text(
            elapsed_minutes=elapsed_minutes,
            node_minutes=matched_node,
            phase=phase,
            progress_status=progress_status,
            progress_details=progress_details,
        )

        await redis_client.setex(lock_key, TIME_NODE_LOCK_TTL_SECONDS, "1")
        await enqueue_task(
            room_id,
            {
                "room_id": room_id,
                "agent_role": "facilitator",
                "reason": reason,
                "strategy": strategy,
                "priority": 1,
                "trigger_type": "time_progress",
                "triggered_at": now,
                "phase": phase,
                "progress_status": progress_status,
                "elapsed_minutes": elapsed_minutes,
                "node_minutes": matched_node,
            },
        )


async def check_online_presence_cleanup() -> None:
    await cleanup_stale_online_presence(stale_seconds=120)


def start_scheduler() -> None:
    if scheduler.running:
        return

    cfg = get_agent_settings()
    scheduler.add_job(check_silence, "interval", seconds=30, id="check_silence", replace_existing=True)
    scheduler.add_job(
        check_time_progress_reminders,
        "interval",
        seconds=30,
        id="check_time_progress_reminders",
        replace_existing=True,
    )
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
    scheduler.add_job(
        check_online_presence_cleanup,
        "interval",
        seconds=60,
        id="cleanup_online_presence",
        replace_existing=True,
    )
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown()

