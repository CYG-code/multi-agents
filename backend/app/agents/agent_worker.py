from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timezone

from app.agents.context_builder import get_recent_messages, get_room_context
from app.agents.queue import dequeue_tasks, requeue_task, set_task_status
from app.agents.role_agents import ROLE_AGENTS
from app.agents.settings import get_agent_settings
from app.agents.trigger_policy import is_user_trigger
from app.db.redis_client import get_redis_client

WORKER_ID = str(uuid.uuid4())
LOCK_TTL_SECONDS = 30
POLL_INTERVAL_SECONDS = 1
AGENT_DEBUG_LOG = os.getenv("AGENT_DEBUG_LOG", "").lower() == "true"


def _agent_log(event: str, extra: dict | None = None) -> None:
    if not AGENT_DEBUG_LOG:
        return
    payload = {
        "event": event,
        "ts": datetime.now(timezone.utc).isoformat(),
        "worker_id": WORKER_ID,
    }
    if extra:
        payload["extra"] = extra
    print("[AGENT-WORKER-DEBUG]", payload, flush=True)


class AgentWorker:
    _global_semaphore: asyncio.Semaphore | None = None
    _global_semaphore_limit: int = 0

    def __init__(self):
        self._running = False

    @classmethod
    def _ensure_global_semaphore(cls, limit: int) -> asyncio.Semaphore:
        safe_limit = max(1, int(limit))
        if cls._global_semaphore is None or cls._global_semaphore_limit != safe_limit:
            cls._global_semaphore = asyncio.Semaphore(safe_limit)
            cls._global_semaphore_limit = safe_limit
        return cls._global_semaphore

    @classmethod
    def _global_running_count(cls) -> int:
        if cls._global_semaphore is None:
            return 0
        available = int(getattr(cls._global_semaphore, "_value", cls._global_semaphore_limit))
        return max(0, cls._global_semaphore_limit - available)

    async def run(self) -> None:
        self._running = True
        print(f"[AgentWorker] started worker_id={WORKER_ID}")
        _agent_log("agent_worker_started")
        while self._running:
            try:
                _agent_log("agent_worker_poll_start")
                await self._process_all_rooms()
            except Exception as exc:
                print(f"[AgentWorker] processing error: {exc}")
                _agent_log("agent_worker_poll_error", {"exception_class": type(exc).__name__, "exception_message": str(exc)})
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    def stop(self) -> None:
        self._running = False

    async def _process_all_rooms(self) -> None:
        redis_client = get_redis_client()
        rooms = await redis_client.smembers("active_rooms")
        _agent_log("agent_worker_rooms_loaded", {"room_count": len(rooms), "rooms": list(rooms)[:20]})
        for room_id in rooms:
            tasks = await dequeue_tasks(room_id)
            for task in tasks:
                await self._execute_task(room_id, task)

    async def _execute_task(self, room_id: str, task: dict) -> None:
        task_id = str(task.get("task_id") or "")
        trigger_type = str(task.get("trigger_type") or "manual")
        source_message_id = task.get("source_message_id")
        _agent_log(
            "agent_worker_task_start",
            {
                "task_id": task_id,
                "room_id": room_id,
                "agent_role": task.get("agent_role"),
                "trigger_type": trigger_type,
                "source_message_id": source_message_id,
            },
        )
        agent_role = (task.get("agent_role") or "").strip().lower()
        if agent_role not in ROLE_AGENTS:
            print(f"[AgentWorker] unknown agent_role={agent_role}")
            _agent_log("agent_worker_task_failed", {"task_id": task_id, "room_id": room_id, "reason": "unknown_role"})
            await set_task_status(
                task_id=task_id,
                room_id=room_id,
                agent_role=agent_role,
                trigger_type=trigger_type,
                status="failed",
                reason="unknown_role",
                source_message_id=source_message_id,
                finished_at=datetime.now(timezone.utc).isoformat(),
                error="unknown_agent_role",
            )
            return

        cfg = get_agent_settings()
        if not self._is_task_enabled(cfg, task, agent_role):
            await self._publish_queue_dropped(
                room_id=room_id,
                task=task,
                reason="disabled",
                message="当前智能体触发条件未启用，本次调用已取消。",
            )
            print(
                f"[AgentWorker] drop disabled task room={room_id} role={agent_role} "
                f"trigger={task.get('trigger_type')} task_id={task.get('task_id')}"
            )
            _agent_log("agent_worker_task_dropped", {"task_id": task_id, "room_id": room_id, "reason": "disabled"})
            await set_task_status(
                task_id=task_id,
                room_id=room_id,
                agent_role=agent_role,
                trigger_type=trigger_type,
                status="dropped",
                reason="disabled",
                source_message_id=source_message_id,
                finished_at=datetime.now(timezone.utc).isoformat(),
                drop_reason="disabled",
            )
            return

        redis_client = get_redis_client()
        trigger_type = (task.get("trigger_type") or "").strip().lower()
        is_auto_trigger = not is_user_trigger(trigger_type)
        room_auto_cooldown_key = f"cooldown:{room_id}:auto_intervention"

        if is_auto_trigger and await redis_client.exists(room_auto_cooldown_key):
            await self._publish_queue_dropped(
                room_id=room_id,
                task=task,
                reason="room_auto_cooldown",
                message="当前房间自动触发冷却中，本次自动调用已取消。",
            )
            print(
                f"[AgentWorker] drop auto task due to room cooldown "
                f"room={room_id} trigger={trigger_type} role={agent_role}"
            )
            _agent_log("agent_worker_task_dropped", {"task_id": task_id, "room_id": room_id, "reason": "room_auto_cooldown"})
            await set_task_status(
                task_id=task_id,
                room_id=room_id,
                agent_role=agent_role,
                trigger_type=trigger_type,
                status="dropped",
                reason="room_auto_cooldown",
                source_message_id=source_message_id,
                finished_at=datetime.now(timezone.utc).isoformat(),
                drop_reason="room_auto_cooldown",
            )
            return

        cooldown_key = f"cooldown:{room_id}:{agent_role}"
        if await redis_client.exists(cooldown_key):
            remaining_seconds = await self._cooldown_remaining_seconds(redis_client, cooldown_key)
            if is_user_trigger(trigger_type):
                await self._publish_queue_dropped(
                    room_id=room_id,
                    task=task,
                    reason="role_cooldown",
                    message=f"当前智能体正在冷却中，请 {remaining_seconds} 秒后再试。",
                )
            else:
                await self._publish_queue_dropped(
                    room_id=room_id,
                    task=task,
                    reason="role_cooldown",
                    message=f"当前智能体冷却中（剩余约 {remaining_seconds} 秒），本次自动调用已取消。",
                )
                print(
                    f"[AgentWorker] drop auto task due to role cooldown "
                    f"room={room_id} role={agent_role} trigger={trigger_type}"
                )
            _agent_log(
                "agent_worker_task_dropped",
                {"task_id": task_id, "room_id": room_id, "reason": "role_cooldown", "remaining_seconds": remaining_seconds},
            )
            await set_task_status(
                task_id=task_id,
                room_id=room_id,
                agent_role=agent_role,
                trigger_type=trigger_type,
                status="dropped",
                reason="role_cooldown",
                source_message_id=source_message_id,
                finished_at=datetime.now(timezone.utc).isoformat(),
                drop_reason="role_cooldown",
            )
            return

        lock_key = f"room:{room_id}:agent_lock"
        _agent_log("agent_lock_acquire_start", {"task_id": task_id, "room_id": room_id, "lock_key": lock_key, "lock_ttl": LOCK_TTL_SECONDS})
        acquired = await redis_client.set(lock_key, WORKER_ID, nx=True, ex=LOCK_TTL_SECONDS)
        if not acquired:
            _agent_log("agent_lock_acquire_failed", {"task_id": task_id, "room_id": room_id, "lock_key": lock_key, "action": "requeue"})
            await requeue_task(room_id, task, delay_seconds=5)
            return
        _agent_log("agent_lock_acquire_success", {"task_id": task_id, "room_id": room_id, "lock_key": lock_key})
        acquired_global_token = False
        global_limit = int(getattr(cfg.timing, "agent_global_concurrency_limit", 3))
        semaphore = self._ensure_global_semaphore(global_limit)
        _agent_log(
            "agent_global_semaphore_acquire_start",
            {
                "task_id": task_id,
                "room_id": room_id,
                "limit": global_limit,
                "running": self._global_running_count(),
            },
        )
        if semaphore.locked():
            _agent_log(
                "agent_global_semaphore_acquire_wait",
                {
                    "task_id": task_id,
                    "room_id": room_id,
                    "limit": global_limit,
                    "running": self._global_running_count(),
                    "action": "requeue",
                },
            )
            await requeue_task(room_id, task, delay_seconds=2)
            return

        await semaphore.acquire()
        acquired_global_token = True
        _agent_log(
            "agent_global_semaphore_acquire_success",
            {
                "task_id": task_id,
                "room_id": room_id,
                "limit": global_limit,
                "running": self._global_running_count(),
            },
        )
        await set_task_status(
            task_id=task_id,
            room_id=room_id,
            agent_role=agent_role,
            trigger_type=trigger_type,
            status="running",
            reason=str(task.get("reason") or ""),
            source_message_id=source_message_id,
            running_at=datetime.now(timezone.utc).isoformat(),
        )
        await self._publish_task_state_event(
            room_id=room_id,
            task_id=task_id,
            agent_role=agent_role,
            source_message_id=source_message_id,
            trigger_type=trigger_type,
            event_type="agent:running",
            status="running",
            message="Agent task is running.",
        )

        try:
            wait_ms = round((time.time() - float(task.get("triggered_at") or time.time())) * 1000, 3)
            _agent_log("agent_worker_task_exec_start", {"task_id": task_id, "room_id": room_id, "wait_ms": wait_ms})
            exec_started = time.perf_counter()
            context = await get_room_context(room_id)
            history = await get_recent_messages(room_id)
            agent = ROLE_AGENTS[agent_role]
            timeout_seconds = max(5, int(getattr(cfg.timing, "agent_response_timeout_seconds", 90)))
            try:
                await asyncio.wait_for(
                    agent.generate_and_push(
                        room_id=room_id,
                        context=context,
                        history=history,
                        source_message_id=task.get("source_message_id"),
                        trigger_type=task.get("trigger_type"),
                        task=task,
                    ),
                    timeout=timeout_seconds,
                )
            except asyncio.TimeoutError:
                print(
                    f"[AgentWorker] timeout room={room_id} role={agent_role} "
                    f"trigger={task.get('trigger_type')} timeout={timeout_seconds}s"
                )
                queue_len = int(await redis_client.zcard(f"agent_queue:{room_id}"))
                lock_exists = bool(await redis_client.exists(lock_key))
                _agent_log(
                    "agent_worker_task_timeout",
                    {
                        "task_id": task_id,
                        "room_id": room_id,
                        "agent_role": agent_role,
                        "wait_ms": wait_ms,
                        "exec_ms": round((time.perf_counter() - exec_started) * 1000, 3),
                        "timeout_seconds": timeout_seconds,
                        "queue_length": queue_len,
                        "lock_exists": lock_exists,
                    },
                )
                await set_task_status(
                    task_id=task_id,
                    room_id=room_id,
                    agent_role=agent_role,
                    trigger_type=trigger_type,
                    status="timeout",
                    reason="worker_timeout",
                    source_message_id=source_message_id,
                    finished_at=datetime.now(timezone.utc).isoformat(),
                    error=f"timeout after {timeout_seconds}s",
                )
                await self._publish_task_state_event(
                    room_id=room_id,
                    task_id=task_id,
                    agent_role=agent_role,
                    source_message_id=source_message_id,
                    trigger_type=trigger_type,
                    event_type="agent:timeout",
                    status="timeout",
                    reason="worker_timeout",
                    message=f"Agent task timed out after {timeout_seconds}s.",
                )
                return

            await redis_client.setex(cooldown_key, cfg.timing.agent_cooldown_seconds, "1")
            if is_auto_trigger:
                await redis_client.setex(
                    room_auto_cooldown_key,
                    int(getattr(cfg.timing, "room_auto_intervention_cooldown_seconds", 180)),
                    "1",
                )
            print(
                f"[AgentWorker] executed room={room_id} role={agent_role} "
                f"trigger={task.get('trigger_type')} reason={task.get('reason')}"
            )
            _agent_log(
                "agent_worker_task_done",
                {
                    "task_id": task_id,
                    "room_id": room_id,
                    "agent_role": agent_role,
                    "wait_ms": wait_ms,
                    "exec_ms": round((time.perf_counter() - exec_started) * 1000, 3),
                },
            )
        except Exception as exc:
            await set_task_status(
                task_id=task_id,
                room_id=room_id,
                agent_role=agent_role,
                trigger_type=trigger_type,
                status="failed",
                reason="worker_exception",
                source_message_id=source_message_id,
                finished_at=datetime.now(timezone.utc).isoformat(),
                error=str(exc),
            )
            await self._publish_task_state_event(
                room_id=room_id,
                task_id=task_id,
                agent_role=agent_role,
                source_message_id=source_message_id,
                trigger_type=trigger_type,
                event_type="agent:failed",
                status="failed",
                reason="worker_exception",
                message="Agent task failed in worker.",
                error=str(exc),
            )
            _agent_log(
                "agent_worker_task_failed",
                {
                    "task_id": task_id,
                    "room_id": room_id,
                    "agent_role": agent_role,
                    "exception_class": type(exc).__name__,
                    "exception_message": str(exc),
                },
            )
            raise
        finally:
            if acquired_global_token:
                semaphore.release()
                _agent_log(
                    "agent_global_semaphore_release",
                    {
                        "task_id": task_id,
                        "room_id": room_id,
                        "limit": global_limit,
                        "running": self._global_running_count(),
                    },
                )
            current_lock = await redis_client.get(lock_key)
            if current_lock == WORKER_ID:
                await redis_client.delete(lock_key)
                _agent_log("agent_lock_release", {"task_id": task_id, "room_id": room_id, "lock_key": lock_key})

    async def _publish_queue_dropped(
        self,
        *,
        room_id: str,
        task: dict,
        reason: str,
        message: str,
    ) -> None:
        source_message_id = task.get("source_message_id")
        agent_role = (task.get("agent_role") or "").strip().lower()
        if not agent_role:
            return

        payload = {
            "type": "agent:queue_dropped",
            "room_id": room_id,
            "source_message_id": source_message_id,
            "agent_role": agent_role,
            "task_id": task.get("task_id"),
            "trigger_type": str(task.get("trigger_type") or "manual"),
            "status": "dropped",
            "reason": reason,
            "message": message,
        }
        await set_task_status(
            task_id=str(task.get("task_id") or ""),
            room_id=room_id,
            agent_role=agent_role,
            trigger_type=str(task.get("trigger_type") or "manual"),
            status="dropped",
            reason=reason,
            source_message_id=source_message_id,
            finished_at=datetime.now(timezone.utc).isoformat(),
            drop_reason=reason,
        )
        _agent_log(
            "agent_dropped_broadcast_start",
            {
                "task_id": task.get("task_id"),
                "room_id": room_id,
                "agent_role": agent_role,
                "reason": reason,
                "source_message_id": source_message_id,
            },
        )
        try:
            redis_client = get_redis_client()
            await redis_client.publish(f"room:{room_id}", json.dumps(payload, ensure_ascii=False))
            _agent_log(
                "agent_dropped_broadcast_done",
                {
                    "task_id": task.get("task_id"),
                    "room_id": room_id,
                    "agent_role": agent_role,
                    "reason": reason,
                },
            )
        except Exception as exc:
            print(
                f"[AgentWorker] publish queue_dropped failed room={room_id} "
                f"role={agent_role} reason={reason} error={exc}"
            )
            _agent_log(
                "agent_dropped_broadcast_failed",
                {
                    "task_id": task.get("task_id"),
                    "room_id": room_id,
                    "agent_role": agent_role,
                    "reason": reason,
                    "exception_class": type(exc).__name__,
                    "exception_message": str(exc),
                },
            )

    async def _publish_task_state_event(
        self,
        *,
        room_id: str,
        task_id: str,
        agent_role: str,
        source_message_id: str | None,
        trigger_type: str,
        event_type: str,
        status: str,
        reason: str | None = None,
        message: str | None = None,
        error: str | None = None,
    ) -> None:
        if not agent_role:
            return
        payload = {
            "type": event_type,
            "room_id": room_id,
            "task_id": task_id,
            "agent_role": agent_role,
            "trigger_type": trigger_type,
            "source_message_id": source_message_id,
            "status": status,
        }
        if reason:
            payload["reason"] = reason
        if message:
            payload["message"] = message
        if error:
            payload["error"] = error
        try:
            redis_client = get_redis_client()
            await redis_client.publish(f"room:{room_id}", json.dumps(payload, ensure_ascii=False))
        except Exception as exc:
            _agent_log(
                "agent_state_broadcast_failed",
                {
                    "task_id": task_id,
                    "room_id": room_id,
                    "event_type": event_type,
                    "exception_class": type(exc).__name__,
                    "exception_message": str(exc),
                },
            )

    @staticmethod
    async def _cooldown_remaining_seconds(redis_client, cooldown_key: str) -> int:
        try:
            ttl = await redis_client.ttl(cooldown_key)
            if isinstance(ttl, int) and ttl > 0:
                return ttl
        except Exception:
            pass
        return 1

    @staticmethod
    def _is_task_enabled(cfg, task: dict, agent_role: str) -> bool:
        trigger_type = (task.get("trigger_type") or "").strip().lower()
        auto_speak = getattr(cfg, "auto_speak", None)

        if trigger_type == "silence" and agent_role == "facilitator":
            facilitator_silence_enabled = (
                True if auto_speak is None else getattr(auto_speak, "facilitator_silence_enabled", True)
            )
            return bool(getattr(cfg.timing, "silence_trigger_enabled", True) and facilitator_silence_enabled)

        if trigger_type == "monopoly" and agent_role == "encourager":
            monopoly_enabled = True if auto_speak is None else getattr(auto_speak, "monopoly_encourager_enabled", True)
            return bool(monopoly_enabled)

        if trigger_type == "committee":
            committee_enabled = True if auto_speak is None else getattr(auto_speak, "committee_enabled", True)
            if not committee_enabled:
                return False

            if agent_role == "devil_advocate":
                return bool(True if auto_speak is None else getattr(auto_speak, "committee_devil_advocate_enabled", True))
            if agent_role == "summarizer":
                return bool(True if auto_speak is None else getattr(auto_speak, "committee_summarizer_enabled", True))
            if agent_role == "encourager":
                return bool(True if auto_speak is None else getattr(auto_speak, "committee_encourager_enabled", True))
            return True

        return True


agent_worker = AgentWorker()
