from __future__ import annotations

import asyncio
import json
import time
from uuid import UUID

from app.agents.context_builder import get_recent_messages, get_room_context, get_room_members
from app.agents.agent_messages import COMMITTEE_DEFAULT_REASON
from app.agents.queue import enqueue_task
from app.agents.settings import get_agent_settings
from app.background_experts import (
    BehavioralEngagementAnalyst,
    ChiefDispatcher,
    CognitiveEngagementAnalyst,
    EmotionalEngagementAnalyst,
    SocialCPSAnalyst,
)
from app.db.redis_client import get_redis_client
from app.db.session import AsyncSessionLocal
from app.models.analysis import AnalysisSnapshot


class BasicCommittee:
    def __init__(self):
        self.cognitive_analyst = CognitiveEngagementAnalyst()
        self.behavioral_analyst = BehavioralEngagementAnalyst()
        self.emotional_analyst = EmotionalEngagementAnalyst()
        self.social_analyst = SocialCPSAnalyst()
        self.dispatcher = ChiefDispatcher()

    async def analyze_and_dispatch(self, room_id: str) -> None:
        messages = await get_recent_messages(room_id, limit=50)
        members = await get_room_members(room_id)
        if not messages:
            return

        cognitive, behavioral, emotional, social = await asyncio.gather(
            self.cognitive_analyst.analyze(messages, members),
            self.behavioral_analyst.analyze(messages, members),
            self.emotional_analyst.analyze(messages, members),
            self.social_analyst.analyze(messages, members),
        )

        context = await get_room_context(room_id)
        recent_rule_triggers = await self._get_recent_rule_triggers(room_id)
        decision = self.dispatcher.dispatch(
            cognitive_report=cognitive,
            behavioral_report=behavioral,
            emotional_report=emotional,
            social_report=social,
            current_phase=context.get("current_phase") or "Unknown",
            recent_interventions=context.get("recent_interventions") or [],
            recent_rule_triggers=recent_rule_triggers,
            recent_same_role_window=max(
                2,
                int(
                    getattr(
                        getattr(get_agent_settings(), "auto_speak", None),
                        "committee_recent_same_role_window",
                        2,
                    )
                ),
            ),
        )

        snapshot_id = await self._save_snapshot(
            room_id=room_id,
            analyzed_message_count=len(messages),
            context=context,
            cognitive=cognitive,
            behavioral=behavioral,
            emotional=emotional,
            social=social,
            decision=decision,
        )
        await self._publish_analysis_update(
            room_id=room_id,
            snapshot_id=snapshot_id,
            cognitive=cognitive,
            behavioral=behavioral,
            emotional=emotional,
            social=social,
            decision=decision,
        )

        if not decision.get("should_intervene"):
            return

        await enqueue_task(
            room_id,
            {
                "room_id": room_id,
                "agent_role": decision.get("selected_agent_role"),
                "trigger_type": decision.get("trigger_type", "committee"),
                "reason": decision.get("reason", COMMITTEE_DEFAULT_REASON),
                "strategy": decision.get("strategy", ""),
                "priority": int(decision.get("priority") or 1),
                "target_dimension": decision.get("target_dimension", "none"),
                "evidence": decision.get("evidence") or [],
                "current_phase": decision.get("current_phase", "unknown"),
                "source_message_id": None,
                "triggered_at": time.time(),
                "snapshot_id": snapshot_id,
                "intervention_id": None,
            },
        )

    async def _get_recent_rule_triggers(self, room_id: str) -> dict:
        try:
            redis_client = get_redis_client()
            return {
                "silence": bool(await redis_client.exists(f"recent_rule_trigger:{room_id}:silence")),
                "time_progress": bool(await redis_client.exists(f"recent_rule_trigger:{room_id}:time_progress")),
                "monopoly": bool(await redis_client.exists(f"recent_rule_trigger:{room_id}:monopoly")),
            }
        except Exception:
            return {"silence": False, "time_progress": False, "monopoly": False}

    async def _save_snapshot(
        self,
        *,
        room_id: str,
        analyzed_message_count: int,
        context: dict,
        cognitive: dict,
        behavioral: dict,
        emotional: dict,
        social: dict,
        decision: dict,
    ) -> str | None:
        try:
            parsed_room_id = UUID(str(room_id))
        except (TypeError, ValueError):
            return None
        try:
            async with AsyncSessionLocal() as db:
                row = AnalysisSnapshot(
                    room_id=parsed_room_id,
                    analyzed_message_count=analyzed_message_count,
                    analysis_context={
                        "current_phase": context.get("current_phase"),
                        "phase_goal": context.get("phase_goal"),
                        "elapsed_minutes": context.get("elapsed_minutes"),
                    },
                    rule_metrics={},
                    cognitive_report=cognitive.get("cognitive_report"),
                    behavioral_report=behavioral.get("behavioral_report"),
                    emotional_report=emotional.get("emotional_report"),
                    social_report=social.get("social_report"),
                    social_cps_report=social.get("social_cps_report"),
                    interaction_report={
                        "compat": True,
                        "behavioral": behavioral.get("behavioral_report"),
                        "social": social.get("social_report"),
                    },
                    diversity_score=cognitive.get("diversity_score"),
                    progress_score=cognitive.get("progress_score"),
                    behavioral_score=behavioral.get("behavioral_score"),
                    social_score=social.get("social_score"),
                    balance_score=(1.0 - max((v.get("score", 0.0) for v in (behavioral.get("participation_scores") or {}).values()), default=0.0)),
                    participation_scores=behavioral.get("participation_scores"),
                    is_single_dominated=behavioral.get("is_single_dominated"),
                    dominant_members=behavioral.get("dominant_members"),
                    silent_members=behavioral.get("silent_members"),
                    emotion_flags=emotional.get("emotion_flags"),
                    should_intervene=bool(decision.get("should_intervene")),
                    selected_agent_role=decision.get("selected_agent_role"),
                    selected_strategy=decision.get("strategy"),
                    dispatcher_decision=decision,
                )
                db.add(row)
                await db.commit()
                await db.refresh(row)
                return str(row.id)
        except Exception:
            return None

    async def _publish_analysis_update(
        self,
        *,
        room_id: str,
        snapshot_id: str | None,
        cognitive: dict,
        behavioral: dict,
        emotional: dict,
        social: dict,
        decision: dict,
    ) -> None:
        try:
            redis_client = get_redis_client()
            payload = {
                "type": "analysis:update",
                "room_id": room_id,
                "snapshot_id": snapshot_id,
                "cognitive_report": cognitive,
                "behavioral_report": behavioral,
                "emotional_report": emotional,
                "social_report": social,
                "social_cps_report": social.get("social_cps_report"),
                "decision": decision,
                "triggered_at": time.time(),
            }
            await redis_client.publish(f"room:{room_id}", json.dumps(payload, ensure_ascii=False))
        except Exception:
            return


basic_committee = BasicCommittee()
