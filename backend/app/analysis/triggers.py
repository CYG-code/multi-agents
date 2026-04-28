from __future__ import annotations

import time

from app.agents.agent_messages import MONOPOLY_REASON_TEMPLATE, MONOPOLY_STRATEGY
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
        rule_marker_ttl = max(30, int(getattr(cfg.timing, "rule_trigger_marker_ttl_seconds", 180)))
        elapsed_seconds = await get_elapsed_seconds_from_timer_start(room_id)
        warmup_seconds = cfg.timing.warmup_minutes * 60
        if elapsed_seconds is None or elapsed_seconds < warmup_seconds:
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
        await redis_client.setex(f"recent_rule_trigger:{room_id}:monopoly", rule_marker_ttl, "1")
        await enqueue_task(
            room_id,
            {
                "room_id": room_id,
                "agent_role": "encourager",
                "reason": MONOPOLY_REASON_TEMPLATE.format(count=threshold),
                "strategy": MONOPOLY_STRATEGY,
                "priority": 2,
                "trigger_type": "monopoly",
                "target_dimension": "behavioral",
                "evidence": [f"monopoly_message_count={threshold}"],
                "current_phase": "unknown",
                "triggered_at": time.time(),
            },
        )


trigger_detector = TriggerDetector()
