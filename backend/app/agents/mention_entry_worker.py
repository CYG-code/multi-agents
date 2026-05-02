from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone

from app.agents.queue import (
    enqueue_task,
    mark_mention_entry_status,
    pop_due_mention_entries,
)
from app.agents.settings import get_agent_settings
from app.websocket.manager import manager

POLL_INTERVAL_SECONDS = 1
AGENT_DEBUG_LOG = os.getenv("AGENT_DEBUG_LOG", "").lower() == "true"


def _agent_log(event: str, extra: dict | None = None) -> None:
    if not AGENT_DEBUG_LOG:
        return
    payload = {
        "event": event,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        payload["extra"] = extra
    print("[MENTION-ENTRY-WORKER-DEBUG]", payload, flush=True)


class MentionEntryWorker:
    def __init__(self) -> None:
        self._running = False

    def stop(self) -> None:
        self._running = False

    async def run(self) -> None:
        self._running = True
        _agent_log("mention_entry_worker_started")
        while self._running:
            try:
                _agent_log("mention_entry_poll_start")
                await self._process_once()
            except Exception as exc:
                _agent_log(
                    "mention_entry_worker_error",
                    {
                        "exception_class": type(exc).__name__,
                        "exception_message": str(exc),
                    },
                )
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    async def _process_once(self) -> int:
        cfg = get_agent_settings()
        if not bool(getattr(cfg.timing, "mention_entry_enabled", False)):
            return 0

        rate = max(1, int(getattr(cfg.timing, "mention_entry_rate_per_sec", 3)))
        entries = await pop_due_mention_entries(rate)
        if not entries:
            return 0

        handled = 0
        now_ts = time.time()
        for entry in entries:
            handled += 1
            await self._handle_entry(entry, now_ts=now_ts)
        return handled

    async def _handle_entry(self, entry: dict[str, str], *, now_ts: float) -> None:
        entry_id = str(entry.get("entry_id") or "")
        room_id = str(entry.get("room_id") or "")
        agent_role = str(entry.get("agent_role") or "")
        source_message_id = str(entry.get("source_message_id") or "")
        trigger_type = str(entry.get("trigger_type") or "mention")
        expire_at = float(entry.get("expire_at") or 0.0)

        if expire_at and now_ts > expire_at:
            await mark_mention_entry_status(
                entry_id,
                "dropped",
                reason="mention_entry_timeout",
            )
            _agent_log(
                "mention_entry_dropped_timeout",
                {
                    "entry_id": entry_id,
                    "room_id": room_id,
                    "agent_role": agent_role,
                },
            )
            await manager.broadcast_to_room(
                room_id,
                {
                    "type": "agent:dropped",
                    "entry_id": entry_id,
                    "source_message_id": source_message_id,
                    "agent_role": agent_role,
                    "trigger_type": trigger_type,
                    "status": "dropped",
                    "reason": "mention_entry_timeout",
                    "message": "Agent mention entry timed out before queueing.",
                },
            )
            return

        try:
            _agent_log(
                "mention_entry_enqueue_start",
                {
                    "entry_id": entry_id,
                    "room_id": room_id,
                    "agent_role": agent_role,
                },
            )
            task = await enqueue_task(
                room_id,
                {
                    "room_id": room_id,
                    "agent_role": agent_role,
                    "reason": str(entry.get("reason") or ""),
                    "strategy": str(entry.get("strategy") or ""),
                    "priority": get_agent_settings().mention.priority,
                    "trigger_type": trigger_type,
                    "target_dimension": "user_request",
                    "evidence": [],
                    "current_phase": "unknown",
                    "student_name": str(entry.get("student_name") or ""),
                    "source_message_id": source_message_id,
                    "triggered_at": now_ts,
                },
            )
            task_id = str(task.get("task_id") or "")
            await mark_mention_entry_status(
                entry_id,
                "queued",
                reason="queued_to_agent_queue",
                task_id=task_id,
            )
            _agent_log(
                "mention_entry_enqueue_done",
                {
                    "entry_id": entry_id,
                    "task_id": task_id,
                    "room_id": room_id,
                    "agent_role": agent_role,
                },
            )
            await manager.broadcast_to_room(
                room_id,
                {
                    "type": "agent:queued",
                    "task_id": task_id,
                    "entry_id": entry_id,
                    "room_id": room_id,
                    "agent_role": agent_role,
                    "source_message_id": source_message_id,
                    "trigger_type": trigger_type,
                    "status": "queued",
                    "message": "Agent request queued.",
                },
            )
        except Exception as exc:
            await mark_mention_entry_status(
                entry_id,
                "failed",
                reason="mention_entry_enqueue_error",
                error=str(exc),
            )
            _agent_log(
                "mention_entry_enqueue_failed",
                {
                    "entry_id": entry_id,
                    "room_id": room_id,
                    "agent_role": agent_role,
                    "exception_class": type(exc).__name__,
                    "exception_message": str(exc),
                },
            )
            await manager.broadcast_to_room(
                room_id,
                {
                    "type": "agent:failed",
                    "entry_id": entry_id,
                    "room_id": room_id,
                    "agent_role": agent_role,
                    "source_message_id": source_message_id,
                    "trigger_type": trigger_type,
                    "status": "failed",
                    "reason": "mention_entry_enqueue_error",
                    "error": str(exc),
                    "message": "Failed to enqueue agent mention entry.",
                },
            )


mention_entry_worker = MentionEntryWorker()
