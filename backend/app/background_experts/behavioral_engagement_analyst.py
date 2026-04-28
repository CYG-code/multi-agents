from __future__ import annotations

from collections import Counter


class BehavioralEngagementAnalyst:
    async def analyze(self, messages: list[dict], members: list[dict]) -> dict:
        member_ids = [str(m.get("id") or "") for m in members if m.get("id")]
        member_names = {str(m.get("id")): m.get("display_name", "") for m in members if m.get("id")}
        student_msgs = [m for m in messages if m.get("sender_type") == "student"]
        counts = Counter(str(m.get("sender_id") or "") for m in student_msgs if m.get("sender_id"))
        total = sum(counts.values())

        participation_scores = {}
        for uid in member_ids:
            c = int(counts.get(uid, 0))
            participation_scores[uid] = {
                "display_name": member_names.get(uid, ""),
                "message_count": c,
                "score": (c / total) if total > 0 else 0.0,
            }

        silent_members = [uid for uid in member_ids if participation_scores[uid]["message_count"] == 0]
        dominant_members = []
        if total > 0:
            for uid in member_ids:
                if participation_scores[uid]["score"] >= 0.55:
                    dominant_members.append(uid)
        is_single_dominated = len(dominant_members) > 0

        active_ratio = 0.0 if not member_ids else (len(member_ids) - len(silent_members)) / len(member_ids)
        dominance_penalty = 0.25 if is_single_dominated else 0.0
        behavioral_score = max(0.0, min(1.0, active_ratio - dominance_penalty))

        return {
            "behavioral_score": round(behavioral_score, 3),
            "participation_scores": participation_scores,
            "silent_members": silent_members,
            "dominant_members": dominant_members,
            "is_single_dominated": is_single_dominated,
            "behavioral_report": {
                "active_ratio": round(active_ratio, 3),
                "student_message_count": len(student_msgs),
                "diagnosis": (
                    "存在参与不足或单人主导。" if behavioral_score < 0.5 else "行为参与整体正常。"
                ),
            },
        }

