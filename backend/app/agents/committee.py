from __future__ import annotations

import asyncio
import time
from collections import Counter

from app.agents.context_builder import get_recent_messages, get_room_members
from app.agents.queue import enqueue_task
from app.agents.settings import get_agent_settings


class BasicCommittee:
    """
    P4 baseline committee.
    Uses lightweight heuristics to produce dispatch tasks and validate full scheduling flow.
    """

    async def analyze_and_dispatch(self, room_id: str) -> None:
        messages = await get_recent_messages(room_id, limit=50)
        members = await get_room_members(room_id)
        if not messages:
            return

        cognitive, emotional, interaction = await asyncio.gather(
            self._cognitive_analysis(messages),
            self._emotional_analysis(messages),
            self._interaction_analysis(messages, members),
        )

        interventions = self._dispatch(cognitive, emotional, interaction)
        for intervention in interventions:
            await enqueue_task(
                room_id,
                {
                    "room_id": room_id,
                    "agent_role": intervention["role"],
                    "reason": intervention["reason"],
                    "strategy": intervention.get("strategy", ""),
                    "priority": intervention["priority"],
                    "trigger_type": "committee",
                    "triggered_at": time.time(),
                },
            )

    async def _cognitive_analysis(self, messages: list[dict]) -> dict:
        unique_senders = len(set(m.get("sender_id") for m in messages if m.get("sender_id")))
        total = len(messages)
        diversity_score = min(unique_senders / max(total * 0.3, 1), 1.0)
        progress_score = min(total / 20, 1.0)
        return {"diversity_score": diversity_score, "progress_score": progress_score}

    async def _emotional_analysis(self, messages: list[dict]) -> dict:
        negative_keywords = ["算了", "没意思", "随便", "无聊", "放弃"]
        conflict_keywords = ["你不对", "你错了", "不可能", "怎么可以"]
        text = " ".join((m.get("content") or "") for m in messages[-10:])
        return {
            "emotion_flags": {
                "passive": any(kw in text for kw in negative_keywords),
                "conflict": any(kw in text for kw in conflict_keywords),
                "anxious": False,
            }
        }

    async def _interaction_analysis(self, messages: list[dict], members: list[dict]) -> dict:
        sender_counts = Counter(
            m.get("sender_id")
            for m in messages
            if m.get("sender_type") == "student" and m.get("sender_id")
        )
        if not sender_counts or not members:
            return {"participation_scores": {}, "balance_score": 0.5}

        values = list(sender_counts.values())
        total = sum(values)
        max_ratio = max(values) / total if total else 0
        return {
            "participation_scores": dict(sender_counts),
            "balance_score": 1.0 - max_ratio,
        }

    def _dispatch(self, cognitive: dict, emotional: dict, interaction: dict) -> list[dict]:
        cfg = get_agent_settings()
        auto_speak = getattr(cfg, "auto_speak", None)
        committee_devil_advocate_enabled = (
            True if auto_speak is None else getattr(auto_speak, "committee_devil_advocate_enabled", True)
        )
        committee_summarizer_enabled = (
            True if auto_speak is None else getattr(auto_speak, "committee_summarizer_enabled", True)
        )
        committee_encourager_enabled = (
            True if auto_speak is None else getattr(auto_speak, "committee_encourager_enabled", True)
        )
        interventions = []

        if committee_devil_advocate_enabled and cognitive["diversity_score"] < cfg.thresholds.diversity_score_threshold:
            interventions.append(
                {
                    "role": "devil_advocate",
                    "reason": (
                        f"观点多样性偏低（{cognitive['diversity_score']:.2f}），"
                        "引入反向思考避免过早收敛。"
                    ),
                    "strategy": "提出一个与当前主流观点相反但合理的假设，要求小组验证。",
                    "priority": 1,
                }
            )

        if committee_summarizer_enabled and emotional["emotion_flags"]["conflict"]:
            interventions.append(
                {
                    "role": "summarizer",
                    "reason": "检测到冲突性表达，先梳理共识与分歧，降低争执成本。",
                    "strategy": "总结双方共识与核心分歧，并给出一个可验证的下一步问题。",
                    "priority": 1,
                }
            )

        if (
            committee_encourager_enabled
            and emotional["emotion_flags"]["passive"]
            and interaction["balance_score"] < cfg.thresholds.balance_score_threshold
        ):
            interventions.append(
                {
                    "role": "encourager",
                    "reason": "出现消极表达且参与不均衡，需激活低参与成员。",
                    "strategy": "温和点名一位低参与同学，邀请其补充一个具体看法。",
                    "priority": 1,
                }
            )

        return interventions


basic_committee = BasicCommittee()
