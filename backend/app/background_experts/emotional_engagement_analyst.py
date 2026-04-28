from __future__ import annotations


class EmotionalEngagementAnalyst:
    async def analyze(self, messages: list[dict], _members: list[dict]) -> dict:
        text = " ".join((m.get("content") or "") for m in messages[-20:])
        passive_keywords = ["算了", "随便", "不想", "放弃", "懒得"]
        conflict_keywords = ["你错了", "不可能", "别说了", "不同意"]
        anxious_keywords = ["来不及", "好难", "紧张", "怎么办"]
        frustrated_keywords = ["烦", "卡住", "崩了", "受不了"]

        emotion_flags = {
            "passive": any(k in text for k in passive_keywords),
            "conflict": any(k in text for k in conflict_keywords),
            "anxious": any(k in text for k in anxious_keywords),
            "frustrated": any(k in text for k in frustrated_keywords),
        }
        penalty = sum(1 for v in emotion_flags.values() if v) * 0.2
        emotional_score = max(0.0, min(1.0, 0.9 - penalty))

        return {
            "emotional_score": round(emotional_score, 3),
            "emotion_flags": emotion_flags,
            "emotional_report": {
                "diagnosis": (
                    "检测到明显情绪风险，需要先稳态再推进。" if penalty >= 0.4 else "情绪状态总体可控。"
                ),
            },
        }

