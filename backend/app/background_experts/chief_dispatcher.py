from __future__ import annotations


class ChiefDispatcher:
    def dispatch(
        self,
        *,
        cognitive_report: dict,
        behavioral_report: dict,
        emotional_report: dict,
        social_report: dict,
        current_phase: str,
        recent_interventions: list[dict],
    ) -> dict:
        _ = current_phase
        _ = recent_interventions

        diversity_score = float(cognitive_report.get("diversity_score") or 0.5)
        behavioral_score = float(behavioral_report.get("behavioral_score") or 0.5)
        emotional_score = float(emotional_report.get("emotional_score") or 0.5)
        social_score = float(social_report.get("social_score") or social_report.get("social_cps_score") or 0.5)

        cps_report = social_report.get("social_cps_report") or {}
        missing_cps_skills = list(cps_report.get("missing_cps_skills") or [])
        cps_distribution = dict(cps_report.get("cps_skill_distribution") or {})

        # CPS-first routing within social dimension
        if "D1" in missing_cps_skills:
            return self._decision(
                role="facilitator",
                target="social",
                reason="社会协作中缺少 D1（监控并维持共享理解）行为。",
                strategy="请主持人引导全组对当前问题理解做一次对齐检查。",
                evidence=["missing_cps_skill=D1"],
            )
        if "D3" in missing_cps_skills:
            return self._decision(
                role="summarizer",
                target="social",
                reason="社会协作中缺少 D3（调整团队组织）行为。",
                strategy="请总结者先梳理现有分工，再由主持人组织必要的分工调整。",
                evidence=["missing_cps_skill=D3"],
            )
        if "B1" in missing_cps_skills:
            return self._decision(
                role="facilitator",
                target="social",
                reason="社会协作中缺少 B1（建立共享表征）行为。",
                strategy="请主持人引导学生明确关键概念定义与边界，确认理解一致。",
                evidence=["missing_cps_skill=B1"],
            )
        c1_c2 = float(cps_distribution.get("C1", 0)) + float(cps_distribution.get("C2", 0))
        d2 = float(cps_distribution.get("D2", 0))
        if c1_c2 >= 2 and d2 <= 0:
            return self._decision(
                role="devil_advocate",
                target="social",
                reason="行动沟通较多但缺少 D2（监控并评价方案结果）行为。",
                strategy="请批判者引导小组用反例和证据检查当前行动结果质量。",
                evidence=[f"C1+C2={c1_c2}", f"D2={d2}"],
            )
        if "A3" in missing_cps_skills or "B3" in missing_cps_skills:
            return self._decision(
                role="facilitator",
                target="social",
                reason="团队角色理解或组织规则不足（A3/B3 缺失）。",
                strategy="请主持人明确角色分工与协作规则，减少并行讨论冲突。",
                evidence=[f"missing={','.join([c for c in ('A3','B3') if c in missing_cps_skills])}"],
            )

        # 4-dimension fallback rules
        if behavioral_score < 0.45:
            return self._decision(
                role="encourager",
                target="behavioral",
                reason="行为投入偏低，存在低参与或单人主导风险。",
                strategy="请鼓励者点名低参与成员补充观点，再由主持人确认下一步分工。",
                evidence=[f"behavioral_score={behavioral_score:.2f}"],
            )
        if social_score < 0.45:
            return self._decision(
                role="facilitator",
                target="social",
                reason="社会投入偏低，出现互动承接不足。",
                strategy="请主持人组织一次结构化回应轮，确保成员彼此承接观点。",
                evidence=[f"social_score={social_score:.2f}"],
            )
        if diversity_score < 0.35:
            return self._decision(
                role="devil_advocate",
                target="cognitive",
                reason="认知投入不足，观点多样性偏低。",
                strategy="请批判者提出关键反例并要求证据验证方案边界。",
                evidence=[f"diversity_score={diversity_score:.2f}"],
            )
        if emotional_score < 0.45 or any(bool(v) for v in (emotional_report.get("emotion_flags") or {}).values()):
            return self._decision(
                role="encourager",
                target="emotional",
                reason="情感投入偏低，出现焦虑/挫败/冲突信号。",
                strategy="请鼓励者先稳态，再推动小步目标确认。",
                evidence=[f"emotional_score={emotional_score:.2f}"],
            )

        return {
            "should_intervene": False,
            "reason": "四维投入总体稳定，建议继续观察，不强制干预。",
            "observe_next": "关注是否出现沉默成员增多、互动承接下降或证据不足。",
            "target_dimension": "none",
            "evidence": [
                f"cognitive={diversity_score:.2f}",
                f"behavioral={behavioral_score:.2f}",
                f"emotional={emotional_score:.2f}",
                f"social={social_score:.2f}",
            ],
        }

    @staticmethod
    def _decision(*, role: str, target: str, reason: str, strategy: str, evidence: list[str]) -> dict:
        return {
            "should_intervene": True,
            "selected_agent_role": role,
            "priority": 1,
            "reason": reason,
            "strategy": strategy,
            "target_dimension": target,
            "evidence": evidence,
        }

