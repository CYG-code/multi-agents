from __future__ import annotations

import time

from app.agents.queue import enqueue_task
from app.agents.settings import get_agent_settings
from app.analysis.timer_phase import get_elapsed_seconds_from_timer_start
from app.db.redis_client import get_redis_client


class TriggerDetector:
    async def check_monopoly(self, room_id: str, sender_id: str) -> None:
        cfg = get_agent_settings()
        auto_speak = getattr(cfg, "auto_speak", None)
        monopoly_encourager_enabled = True if auto_speak is None else getattr(auto_speak, "monopoly_encourager_enabled", True)
        if not monopoly_encourager_enabled:
            return

        threshold = max(2, int(cfg.thresholds.monopoly_message_count))
        elapsed_seconds = await get_elapsed_seconds_from_timer_start(room_id)
        warmup_seconds = cfg.timing.warmup_minutes * 60
        if elapsed_seconds is None or elapsed_seconds < warmup_seconds:
            # Monopoly trigger is disabled before teacher starts timer and during warmup.
            return

        redis_client = get_redis_client()
        key = f"room:{room_id}:recent_senders"
        await redis_client.lpush(key, sender_id)
        await redis_client.ltrim(key, 0, threshold - 1)
        await redis_client.expire(key, 3600)

        recent = await redis_client.lrange(key, 0, -1)
        if len(recent) != threshold or len(set(recent)) != 1:
            return

        lock_key = f"trigger_lock:{room_id}:monopoly"
        if await redis_client.exists(lock_key):
            return

        await redis_client.setex(lock_key, 60, "1")
        await enqueue_task(
            room_id,
            {
                "room_id": room_id,
                "agent_role": "encourager",
                "reason": f"同一成员连续发送了 {threshold} 条消息，邀请其他成员参与。",
                "strategy": "点名一位暂未发言或发言较少的同学，邀请其补充观点。",
                "priority": 2,
                "trigger_type": "monopoly",
                "triggered_at": time.time(),
            },
        )


trigger_detector = TriggerDetector()

