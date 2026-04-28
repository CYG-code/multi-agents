from __future__ import annotations

import asyncio
import time
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
            print(
                f"[AgentWorker] drop disabled task room={room_id} role={agent_role} "
                f"trigger={task.get('trigger_type')} task_id={task.get('task_id')}"
            )
            return

        redis_client = get_redis_client()
        trigger_type = (task.get("trigger_type") or "").strip().lower()
        is_auto_trigger = not is_user_trigger(trigger_type)
        room_auto_cooldown_key = f"cooldown:{room_id}:auto_intervention"

        hourly_key = f"interventions:{room_id}:{int(time.time() // 3600)}"
        hourly_count = await redis_client.get(hourly_key)
        if hourly_count and int(hourly_count) >= cfg.timing.global_intervention_limit_per_hour:
            print(f"[AgentWorker] room={room_id} hit hourly limit, drop task {task.get('task_id')}")
            return

        if is_auto_trigger and await redis_client.exists(room_auto_cooldown_key):
            print(
                f"[AgentWorker] drop auto task due to room cooldown "
                f"room={room_id} trigger={trigger_type} role={agent_role}"
            )
            return

        cooldown_key = f"cooldown:{room_id}:{agent_role}"
        if await redis_client.exists(cooldown_key):
            if is_user_trigger(trigger_type):
                await requeue_task(room_id, task, delay_seconds=10)
            else:
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
            await agent.generate_and_push(
                room_id=room_id,
                context=context,
                history=history,
                source_message_id=task.get("source_message_id"),
                trigger_type=task.get("trigger_type"),
                task=task,
            )

            await redis_client.setex(cooldown_key, cfg.timing.agent_cooldown_seconds, "1")
            if is_auto_trigger:
                await redis_client.setex(
                    room_auto_cooldown_key,
                    int(getattr(cfg.timing, "room_auto_intervention_cooldown_seconds", 180)),
                    "1",
                )
            current_count = await redis_client.incr(hourly_key)
            if current_count == 1:
                await redis_client.expire(hourly_key, 3600)
            print(
                f"[AgentWorker] executed room={room_id} role={agent_role} "
                f"trigger={task.get('trigger_type')} reason={task.get('reason')}"
            )
        finally:
            current_lock = await redis_client.get(lock_key)
            if current_lock == WORKER_ID:
                await redis_client.delete(lock_key)

    @staticmethod
    def _is_task_enabled(cfg, task: dict, agent_role: str) -> bool:
        trigger_type = (task.get("trigger_type") or "").strip().lower()
        auto_speak = getattr(cfg, "auto_speak", None)

        # Silence-triggered facilitator intervention.
        if trigger_type == "silence" and agent_role == "facilitator":
            facilitator_silence_enabled = (
                True if auto_speak is None else getattr(auto_speak, "facilitator_silence_enabled", True)
            )
            return bool(getattr(cfg.timing, "silence_trigger_enabled", True) and facilitator_silence_enabled)

        # Monopoly-triggered encourager intervention.
        if trigger_type == "monopoly" and agent_role == "encourager":
            monopoly_enabled = True if auto_speak is None else getattr(auto_speak, "monopoly_encourager_enabled", True)
            return bool(monopoly_enabled)

        # Committee-triggered interventions.
        if trigger_type == "committee":
            committee_enabled = True if auto_speak is None else getattr(auto_speak, "committee_enabled", True)
            if not committee_enabled:
                return False

            if agent_role == "devil_advocate":
                return bool(
                    True
                    if auto_speak is None
                    else getattr(auto_speak, "committee_devil_advocate_enabled", True)
                )
            if agent_role == "summarizer":
                return bool(
                    True
                    if auto_speak is None
                    else getattr(auto_speak, "committee_summarizer_enabled", True)
                )
            if agent_role == "encourager":
                return bool(
                    True
                    if auto_speak is None
                    else getattr(auto_speak, "committee_encourager_enabled", True)
                )
            return True

        # Mention/debug/manual task types are intentionally not auto-speak gated.
        return True


agent_worker = AgentWorker()
