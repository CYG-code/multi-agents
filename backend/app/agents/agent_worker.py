from __future__ import annotations

import asyncio
import json
import uuid

from app.agents.context_builder import get_recent_messages, get_room_context
from app.agents.queue import dequeue_tasks, requeue_task
from app.agents.role_agents import ROLE_AGENTS
from app.agents.settings import get_agent_settings
from app.agents.trigger_policy import is_user_trigger
from app.db.redis_client import get_redis_client

WORKER_ID = str(uuid.uuid4())
LOCK_TTL_SECONDS = 30
POLL_INTERVAL_SECONDS = 1


class AgentWorker:
    def __init__(self):
        self._running = False

    async def run(self) -> None:
        self._running = True
        print(f"[AgentWorker] started worker_id={WORKER_ID}")
        while self._running:
            try:
                await self._process_all_rooms()
            except Exception as exc:
                print(f"[AgentWorker] processing error: {exc}")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    def stop(self) -> None:
        self._running = False

    async def _process_all_rooms(self) -> None:
        redis_client = get_redis_client()
        rooms = await redis_client.smembers("active_rooms")
        for room_id in rooms:
            tasks = await dequeue_tasks(room_id)
            for task in tasks:
                await self._execute_task(room_id, task)

    async def _execute_task(self, room_id: str, task: dict) -> None:
        agent_role = (task.get("agent_role") or "").strip().lower()
        if agent_role not in ROLE_AGENTS:
            print(f"[AgentWorker] unknown agent_role={agent_role}")
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
            return

        lock_key = f"room:{room_id}:agent_lock"
        acquired = await redis_client.set(lock_key, WORKER_ID, nx=True, ex=LOCK_TTL_SECONDS)
        if not acquired:
            await requeue_task(room_id, task, delay_seconds=5)
            return

        try:
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
                await requeue_task(room_id, task, delay_seconds=5)
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
        finally:
            current_lock = await redis_client.get(lock_key)
            if current_lock == WORKER_ID:
                await redis_client.delete(lock_key)

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
        if not source_message_id or not agent_role:
            return

        payload = {
            "type": "agent:queue_dropped",
            "source_message_id": source_message_id,
            "agent_role": agent_role,
            "task_id": task.get("task_id"),
            "status": "failed",
            "reason": reason,
            "message": message,
        }
        try:
            redis_client = get_redis_client()
            await redis_client.publish(f"room:{room_id}", json.dumps(payload, ensure_ascii=False))
        except Exception as exc:
            print(
                f"[AgentWorker] publish queue_dropped failed room={room_id} "
                f"role={agent_role} reason={reason} error={exc}"
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
