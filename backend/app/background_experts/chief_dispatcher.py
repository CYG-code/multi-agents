from __future__ import annotations

from app.agents.agent_messages import (
    COMMITTEE_DEFAULT_REASON,
    D_REASON,
    D_STRATEGY,
    LOW_BEHAVIOR_REASON,
    LOW_BEHAVIOR_STRATEGY,
    LOW_COGNITIVE_REASON,
    LOW_COGNITIVE_STRATEGY,
    LOW_EMOTIONAL_REASON,
    LOW_EMOTIONAL_STRATEGY,
    LOW_SOCIAL_REASON,
    LOW_SOCIAL_STRATEGY,
    OBSERVE_NEXT,
    OBSERVE_REASON,
    SOCIAL_D2_REASON,
    SOCIAL_D2_STRATEGY,
    SOCIAL_ROLE_ORG_REASON,
    SOCIAL_ROLE_ORG_STRATEGY,
    SUPPRESS_MONOPOLY_OBSERVE,
    SUPPRESS_MONOPOLY_REASON,
    SUPPRESS_SILENCE_OBSERVE,
    SUPPRESS_SILENCE_REASON,
)


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
        recent_rule_triggers: dict | None = None,
        recent_same_role_window: int = 2,
    ) -> dict:
        recent_rule_triggers = recent_rule_triggers or {}
        phase_value = str(current_phase or "unknown")

        diversity_score = float(cognitive_report.get("diversity_score") or 0.5)
        behavioral_score = float(behavioral_report.get("behavioral_score") or 0.5)
        emotional_score = float(emotional_report.get("emotional_score") or 0.5)
        social_score = float(social_report.get("social_score") or social_report.get("social_cps_score") or 0.5)

        cps_report = social_report.get("social_cps_report") or {}
        missing_cps_skills = list(cps_report.get("missing_cps_skills") or [])
        cps_distribution = dict(cps_report.get("cps_skill_distribution") or {})
        recent_silence = bool(recent_rule_triggers.get("silence"))
        recent_time_progress = bool(recent_rule_triggers.get("time_progress"))
        recent_monopoly = bool(recent_rule_triggers.get("monopoly"))

        role_repeat_window = max(2, int(recent_same_role_window))

        if "D1" in missing_cps_skills and not recent_time_progress:
            suppressed = self._suppress_if_recent_same_role(
                recent_interventions=recent_interventions,
                current_phase=phase_value,
                candidate_role="facilitator",
                target="social",
                reason="近期主持人已多次干预，委员会本轮避免重复同角色发言。",
                window=role_repeat_window,
            )
            if suppressed:
                return suppressed
            return self._validate_decision(
                self._intervene(
                    role="facilitator",
                    target="social",
                    reason=D_REASON["D1"],
                    strategy=D_STRATEGY["D1"],
                    evidence=["missing_cps_skill=D1"],
                    current_phase=phase_value,
                )
            )
        if "D3" in missing_cps_skills and not recent_time_progress:
            suppressed = self._suppress_if_recent_same_role(
                recent_interventions=recent_interventions,
                current_phase=phase_value,
                candidate_role="summarizer",
                target="social",
                reason="近期总结者已多次干预，委员会本轮避免重复同角色发言。",
                window=role_repeat_window,
            )
            if suppressed:
                return suppressed
            return self._validate_decision(
                self._intervene(
                    role="summarizer",
                    target="social",
                    reason=D_REASON["D3"],
                    strategy=D_STRATEGY["D3"],
                    evidence=["missing_cps_skill=D3"],
                    current_phase=phase_value,
                )
            )
        if "B1" in missing_cps_skills and not recent_time_progress:
            suppressed = self._suppress_if_recent_same_role(
                recent_interventions=recent_interventions,
                current_phase=phase_value,
                candidate_role="facilitator",
                target="social",
                reason="近期主持人已多次干预，委员会本轮避免重复同角色发言。",
                window=role_repeat_window,
            )
            if suppressed:
                return suppressed
            return self._validate_decision(
                self._intervene(
                    role="facilitator",
                    target="social",
                    reason=D_REASON["B1"],
                    strategy=D_STRATEGY["B1"],
                    evidence=["missing_cps_skill=B1"],
                    current_phase=phase_value,
                )
            )

        c1_c2 = float(cps_distribution.get("C1", 0)) + float(cps_distribution.get("C2", 0))
        d2 = float(cps_distribution.get("D2", 0))
        if c1_c2 >= 2 and d2 <= 0:
            suppressed = self._suppress_if_recent_same_role(
                recent_interventions=recent_interventions,
                current_phase=phase_value,
                candidate_role="devil_advocate",
                target="social",
                reason="近期批判者已多次干预，委员会本轮避免重复同角色发言。",
                window=role_repeat_window,
            )
            if suppressed:
                return suppressed
            return self._validate_decision(
                self._intervene(
                    role="devil_advocate",
                    target="social",
                    reason=SOCIAL_D2_REASON,
                    strategy=SOCIAL_D2_STRATEGY,
                    evidence=[f"C1+C2={c1_c2}", f"D2={d2}"],
                    current_phase=phase_value,
                )
            )

        if ("A3" in missing_cps_skills or "B3" in missing_cps_skills) and not recent_time_progress:
            missing_codes = ",".join([c for c in ("A3", "B3") if c in missing_cps_skills])
            suppressed = self._suppress_if_recent_same_role(
                recent_interventions=recent_interventions,
                current_phase=phase_value,
                candidate_role="facilitator",
                target="social",
                reason="近期主持人已多次干预，委员会本轮避免重复同角色发言。",
                window=role_repeat_window,
            )
            if suppressed:
                return suppressed
            return self._validate_decision(
                self._intervene(
                    role="facilitator",
                    target="social",
                    reason=SOCIAL_ROLE_ORG_REASON,
                    strategy=SOCIAL_ROLE_ORG_STRATEGY,
                    evidence=[f"missing={missing_codes}"],
                    current_phase=phase_value,
                )
            )

        if behavioral_score < 0.45:
            if recent_monopoly:
                return self._validate_decision(
                    self._suppress(
                        target="behavioral",
                        reason=SUPPRESS_MONOPOLY_REASON,
                        evidence=["recent_rule_trigger=monopoly"],
                        current_phase=phase_value,
                        observe_next=SUPPRESS_MONOPOLY_OBSERVE,
                    )
                )
            suppressed = self._suppress_if_recent_same_role(
                recent_interventions=recent_interventions,
                current_phase=phase_value,
                candidate_role="encourager",
                target="behavioral",
                reason="近期鼓励者已多次干预，委员会本轮避免重复同角色发言。",
                window=role_repeat_window,
            )
            if suppressed:
                return suppressed
            return self._validate_decision(
                self._intervene(
                    role="encourager",
                    target="behavioral",
                    reason=LOW_BEHAVIOR_REASON,
                    strategy=LOW_BEHAVIOR_STRATEGY,
                    evidence=[f"behavioral_score={behavioral_score:.2f}"],
                    current_phase=phase_value,
                )
            )

        if social_score < 0.45:
            if recent_silence:
                return self._validate_decision(
                    self._suppress(
                        target="social",
                        reason=SUPPRESS_SILENCE_REASON,
                        evidence=["recent_rule_trigger=silence"],
                        current_phase=phase_value,
                        observe_next=SUPPRESS_SILENCE_OBSERVE,
                    )
                )
            suppressed = self._suppress_if_recent_same_role(
                recent_interventions=recent_interventions,
                current_phase=phase_value,
                candidate_role="facilitator",
                target="social",
                reason="近期主持人已多次干预，委员会本轮避免重复同角色发言。",
                window=role_repeat_window,
            )
            if suppressed:
                return suppressed
            return self._validate_decision(
                self._intervene(
                    role="facilitator",
                    target="social",
                    reason=LOW_SOCIAL_REASON,
                    strategy=LOW_SOCIAL_STRATEGY,
                    evidence=[f"social_score={social_score:.2f}"],
                    current_phase=phase_value,
                )
            )

        if diversity_score < 0.35:
            suppressed = self._suppress_if_recent_same_role(
                recent_interventions=recent_interventions,
                current_phase=phase_value,
                candidate_role="devil_advocate",
                target="cognitive",
                reason="近期批判者已多次干预，委员会本轮避免重复同角色发言。",
                window=role_repeat_window,
            )
            if suppressed:
                return suppressed
            return self._validate_decision(
                self._intervene(
                    role="devil_advocate",
                    target="cognitive",
                    reason=LOW_COGNITIVE_REASON,
                    strategy=LOW_COGNITIVE_STRATEGY,
                    evidence=[f"diversity_score={diversity_score:.2f}"],
                    current_phase=phase_value,
                )
            )

        if emotional_score < 0.45 or any(bool(v) for v in (emotional_report.get("emotion_flags") or {}).values()):
            suppressed = self._suppress_if_recent_same_role(
                recent_interventions=recent_interventions,
                current_phase=phase_value,
                candidate_role="encourager",
                target="emotional",
                reason="近期鼓励者已多次干预，委员会本轮避免重复同角色发言。",
                window=role_repeat_window,
            )
            if suppressed:
                return suppressed
            return self._validate_decision(
                self._intervene(
                    role="encourager",
                    target="emotional",
                    reason=LOW_EMOTIONAL_REASON,
                    strategy=LOW_EMOTIONAL_STRATEGY,
                    evidence=[f"emotional_score={emotional_score:.2f}"],
                    current_phase=phase_value,
                )
            )

        return self._validate_decision(
            self._observe(
                reason=OBSERVE_REASON,
                evidence=[
                    f"cognitive={diversity_score:.2f}",
                    f"behavioral={behavioral_score:.2f}",
                    f"emotional={emotional_score:.2f}",
                    f"social={social_score:.2f}",
                ],
                current_phase=phase_value,
                observe_next=OBSERVE_NEXT,
            )
        )

    def _suppress_if_recent_same_role(
        self,
        *,
        recent_interventions: list[dict],
        current_phase: str,
        candidate_role: str,
        target: str,
        reason: str,
        window: int = 2,
    ) -> dict | None:
        if not recent_interventions:
            return None
        recent_roles = [str(i.get("agent_role") or "").strip().lower() for i in recent_interventions[:window]]
        if recent_roles.count(candidate_role) >= window:
            return self._validate_decision(
                self._suppress(
                    target=target,
                    reason=reason,
                    evidence=[f"recent_roles={recent_roles}"],
                    current_phase=current_phase,
                    observe_next="观察不同维度是否出现新的高优先级信号。",
                )
            )
        return None

    @staticmethod
    def _intervene(
        *,
        role: str,
        target: str,
        reason: str,
        strategy: str,
        evidence: list[str],
        current_phase: str,
        priority: int = 1,
    ) -> dict:
        return {
            "decision_type": "intervene",
            "should_intervene": True,
            "selected_agent_role": role,
            "trigger_type": "committee",
            "dispatch_source": "chief_dispatcher",
            "target_dimension": target,
            "reason": reason,
            "strategy": strategy,
            "evidence": evidence or [],
            "priority": priority,
            "current_phase": current_phase,
            "observe_next": None,
        }

    @staticmethod
    def _observe(
        *,
        reason: str,
        evidence: list[str],
        current_phase: str,
        observe_next: str = "",
    ) -> dict:
        return {
            "decision_type": "observe",
            "should_intervene": False,
            "selected_agent_role": None,
            "trigger_type": "committee",
            "dispatch_source": "chief_dispatcher",
            "target_dimension": "none",
            "reason": reason,
            "strategy": None,
            "evidence": evidence or [],
            "priority": None,
            "current_phase": current_phase,
            "observe_next": observe_next,
        }

    @staticmethod
    def _suppress(
        *,
        target: str,
        reason: str,
        evidence: list[str],
        current_phase: str,
        observe_next: str = "",
    ) -> dict:
        return {
            "decision_type": "suppress",
            "should_intervene": False,
            "selected_agent_role": None,
            "trigger_type": "committee",
            "dispatch_source": "chief_dispatcher",
            "target_dimension": target,
            "reason": reason,
            "strategy": None,
            "evidence": evidence or [],
            "priority": None,
            "current_phase": current_phase,
            "observe_next": observe_next,
        }

    @staticmethod
    def _validate_decision(decision: dict) -> dict:
        required = [
            "decision_type",
            "should_intervene",
            "selected_agent_role",
            "trigger_type",
            "dispatch_source",
            "target_dimension",
            "reason",
            "strategy",
            "evidence",
            "priority",
            "current_phase",
            "observe_next",
        ]
        for key in required:
            decision.setdefault(key, None)

        if decision["should_intervene"]:
            if not decision["selected_agent_role"]:
                raise ValueError("intervention decision missing selected_agent_role")
            if not decision["reason"]:
                raise ValueError("intervention decision missing reason")
            if not decision["strategy"]:
                raise ValueError("intervention decision missing strategy")

        return decision
