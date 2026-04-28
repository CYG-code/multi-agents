from __future__ import annotations


class CognitiveEngagementAnalyst:
    async def analyze(self, messages: list[dict], _members: list[dict]) -> dict:
        student_msgs = [m for m in messages if m.get("sender_type") == "student"]
        unique_students = len({str(m.get("sender_id") or "") for m in student_msgs if m.get("sender_id")})
        total_student = max(1, len(student_msgs))
        diversity_score = min(unique_students / total_student * 2.0, 1.0)
        progress_score = min(len(messages) / 30.0, 1.0)

        return {
            "diversity_score": round(diversity_score, 3),
            "progress_score": round(progress_score, 3),
            "cognitive_report": {
                "student_message_count": len(student_msgs),
                "unique_student_senders": unique_students,
                "diagnosis": (
                    "观点分布偏单一，建议引入反例验证。" if diversity_score < 0.4 else "观点分布尚可，继续推进证据化讨论。"
                ),
            },
        }

