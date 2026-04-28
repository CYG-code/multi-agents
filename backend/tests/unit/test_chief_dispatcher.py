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
    assert decision["decision_type"] == "intervene"
    assert decision["trigger_type"] == "committee"
    assert decision["dispatch_source"] == "chief_dispatcher"
    assert decision["current_phase"] == "中期"


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
    assert decision["decision_type"] == "intervene"


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
    assert decision["decision_type"] == "intervene"


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
    assert decision["decision_type"] == "intervene"


def test_dispatch_skips_behavioral_when_recent_monopoly():
    dispatcher = ChiefDispatcher()
    decision = dispatcher.dispatch(
        cognitive_report={"diversity_score": 0.8},
        behavioral_report={"behavioral_score": 0.2},
        emotional_report={"emotional_score": 0.9, "emotion_flags": {}},
        social_report={"social_score": 0.8},
        current_phase="中期",
        recent_interventions=[],
        recent_rule_triggers={"monopoly": True},
    )
    assert decision["should_intervene"] is False
    assert "monopoly" in "".join(decision["evidence"])
    assert decision["decision_type"] == "suppress"


def test_dispatch_skips_social_when_recent_silence():
    dispatcher = ChiefDispatcher()
    decision = dispatcher.dispatch(
        cognitive_report={"diversity_score": 0.8},
        behavioral_report={"behavioral_score": 0.8},
        emotional_report={"emotional_score": 0.9, "emotion_flags": {}},
        social_report={"social_score": 0.2},
        current_phase="中期",
        recent_interventions=[],
        recent_rule_triggers={"silence": True},
    )
    assert decision["should_intervene"] is False
    assert decision["decision_type"] == "suppress"


def test_dispatch_observe_shape_when_stable():
    dispatcher = ChiefDispatcher()
    decision = dispatcher.dispatch(
        cognitive_report={"diversity_score": 0.8},
        behavioral_report={"behavioral_score": 0.8},
        emotional_report={"emotional_score": 0.9, "emotion_flags": {}},
        social_report={"social_score": 0.8, "social_cps_report": {"missing_cps_skills": []}},
        current_phase="middle",
        recent_interventions=[],
        recent_rule_triggers={},
    )
    assert decision["should_intervene"] is False
    assert decision["decision_type"] == "observe"
    assert decision["trigger_type"] == "committee"
    assert decision["dispatch_source"] == "chief_dispatcher"
    assert decision["current_phase"] == "middle"


def test_dispatch_suppresses_when_same_role_recently_repeated():
    dispatcher = ChiefDispatcher()
    decision = dispatcher.dispatch(
        cognitive_report={"diversity_score": 0.8},
        behavioral_report={"behavioral_score": 0.8},
        emotional_report={"emotional_score": 0.9, "emotion_flags": {}},
        social_report={"social_cps_report": {"missing_cps_skills": ["D1"]}},
        current_phase="middle",
        recent_interventions=[{"agent_role": "facilitator"}, {"agent_role": "facilitator"}],
        recent_rule_triggers={},
    )
    assert decision["should_intervene"] is False
    assert decision["decision_type"] == "suppress"
    assert "recent_roles" in "".join(decision["evidence"])


def test_dispatch_recent_role_window_is_configurable():
    dispatcher = ChiefDispatcher()
    decision = dispatcher.dispatch(
        cognitive_report={"diversity_score": 0.8},
        behavioral_report={"behavioral_score": 0.8},
        emotional_report={"emotional_score": 0.9, "emotion_flags": {}},
        social_report={"social_cps_report": {"missing_cps_skills": ["D1"]}},
        current_phase="middle",
        recent_interventions=[{"agent_role": "facilitator"}, {"agent_role": "facilitator"}],
        recent_rule_triggers={},
        recent_same_role_window=3,
    )
    assert decision["should_intervene"] is True
    assert decision["selected_agent_role"] == "facilitator"


def test_dispatch_window_one_is_clamped_and_can_still_suppress():
    dispatcher = ChiefDispatcher()
    decision = dispatcher.dispatch(
        cognitive_report={"diversity_score": 0.8},
        behavioral_report={"behavioral_score": 0.8},
        emotional_report={"emotional_score": 0.9, "emotion_flags": {}},
        social_report={"social_cps_report": {"missing_cps_skills": ["D1"]}},
        current_phase="middle",
        recent_interventions=[{"agent_role": "facilitator"}, {"agent_role": "facilitator"}],
        recent_rule_triggers={},
        recent_same_role_window=1,
    )
    assert decision["should_intervene"] is False
    assert decision["decision_type"] == "suppress"
