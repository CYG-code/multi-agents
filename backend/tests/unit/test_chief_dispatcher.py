from app.background_experts.chief_dispatcher import ChiefDispatcher


def test_dispatch_behavioral_low_prefers_encourager():
    dispatcher = ChiefDispatcher()
    decision = dispatcher.dispatch(
        cognitive_report={"diversity_score": 0.8},
        behavioral_report={"behavioral_score": 0.3},
        emotional_report={"emotional_score": 0.9, "emotion_flags": {}},
        social_report={"social_score": 0.9},
        current_phase="中期",
        recent_interventions=[],
    )
    assert decision["should_intervene"] is True
    assert decision["selected_agent_role"] == "encourager"
    assert decision["target_dimension"] == "behavioral"


def test_dispatch_social_low_prefers_facilitator():
    dispatcher = ChiefDispatcher()
    decision = dispatcher.dispatch(
        cognitive_report={"diversity_score": 0.8},
        behavioral_report={"behavioral_score": 0.8},
        emotional_report={"emotional_score": 0.9, "emotion_flags": {}},
        social_report={"social_score": 0.3},
        current_phase="中期",
        recent_interventions=[],
    )
    assert decision["should_intervene"] is True
    assert decision["selected_agent_role"] == "facilitator"
    assert decision["target_dimension"] == "social"


def test_dispatch_missing_d1_prefers_facilitator():
    dispatcher = ChiefDispatcher()
    decision = dispatcher.dispatch(
        cognitive_report={"diversity_score": 0.8},
        behavioral_report={"behavioral_score": 0.8},
        emotional_report={"emotional_score": 0.9, "emotion_flags": {}},
        social_report={"social_cps_report": {"missing_cps_skills": ["D1"]}},
        current_phase="中期",
        recent_interventions=[],
    )
    assert decision["should_intervene"] is True
    assert decision["selected_agent_role"] == "facilitator"
    assert "D1" in "".join(decision["evidence"])


def test_dispatch_missing_d3_prefers_summarizer():
    dispatcher = ChiefDispatcher()
    decision = dispatcher.dispatch(
        cognitive_report={"diversity_score": 0.8},
        behavioral_report={"behavioral_score": 0.8},
        emotional_report={"emotional_score": 0.9, "emotion_flags": {}},
        social_report={"social_cps_report": {"missing_cps_skills": ["D3"]}},
        current_phase="中期",
        recent_interventions=[],
    )
    assert decision["should_intervene"] is True
    assert decision["selected_agent_role"] == "summarizer"
