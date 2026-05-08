from __future__ import annotations

import re

import pytest

from app.agents.role_agents import ROLE_AGENTS


FRONTEND_AGENT_ROLES = (
    "facilitator",
    "resource_finder",
    "summarizer",
    "devil_advocate",
    "concept_explainer",
    "encourager",
)

ROLE_DISPLAY = {
    "facilitator": "???",
    "resource_finder": "?????",
    "summarizer": "???",
    "devil_advocate": "???",
    "concept_explainer": "?????",
    "encourager": "???",
}

INTENT_TARGET = {
    "task_planning": "facilitator",
    "resource_search": "resource_finder",
    "summarization": "summarizer",
    "critique": "devil_advocate",
    "concept_explanation": "concept_explainer",
    "emotional_support": "encourager",
}

# Use ASCII-only requests to avoid terminal encoding side effects.
INTENT_REQUEST = {
    "task_planning": "What should we do next? Help split tasks and assign roles.",
    "resource_search": "Find references, literature, datasets, and evidence.",
    "summarization": "Please summarize current consensus and disagreements.",
    "critique": "Find weaknesses, risks, and counterexamples in our argument.",
    "concept_explanation": "Explain this concept and theory in simple terms.",
    "emotional_support": "I feel anxious and afraid I am holding the team back.",
}

INTENT_KEYWORDS = {
    "task_planning": ("next", "split", "assign", "planning", "workflow", "process"),
    "resource_search": ("reference", "literature", "dataset", "data", "evidence", "source", "materials"),
    "summarization": ("summarize", "consensus", "disagreement", "recap"),
    "critique": ("weakness", "risk", "counterexample", "critique", "challenge"),
    "concept_explanation": ("concept", "theory", "term", "explain", "simple"),
    "emotional_support": ("anxious", "afraid", "stressed", "frustrated", "emotion"),
}

ROLE_CONTRACT_KEYWORDS = {
    "facilitator": ("facilitator", "???", "??", "??", "??"),
    "resource_finder": ("resource_finder", "?????", "??", "??", "??"),
    "summarizer": ("summarizer", "???", "??", "??", "??"),
    "devil_advocate": ("devil_advocate", "???", "??", "??", "??"),
    "concept_explainer": ("concept_explainer", "?????", "??", "??", "??"),
    "encourager": ("encourager", "???", "??", "??", "??"),
}

SOFT_REFERRAL_HINTS = (
    "more suitable",
    "better handled by",
    "can be handled by",
    "????",
    "????",
    "????",
    "???",
)
STIFF_REFUSAL_PHRASES = (
    "I cannot answer",
    "not my responsibility",
    "not allowed",
    "switch to another agent",
    "I cannot help",
    "forbidden"
)


def _build_prompt(agent_role: str, user_request: str) -> str:
    agent = ROLE_AGENTS[agent_role]
    context = {
        "task_description": "Urban heat island collaborative assignment",
        "task_workflow": "idea -> evidence -> report",
        "members_info": "3 students",
        "current_phase": "discussion",
    }
    task = {
        "trigger_type": "mention",
        "reason": f"Student request: {user_request}",
        "strategy": "Follow role boundary and refer to the right role when out-of-domain.",
        "student_name": "StudentA",
    }
    return agent.build_system_prompt(context=context, task=task)


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(k.lower() in low for k in keywords)


def _mentions_role(text: str, role_key: str) -> bool:
    return role_key in text or ROLE_DISPLAY[role_key] in text


def classify_test_request_intent(text: str) -> str:
    low = text.lower()
    # Resource keywords take priority over planning keywords
    if any(k in low for k in INTENT_KEYWORDS["resource_search"]):
        return "resource_search"
    for intent, kws in INTENT_KEYWORDS.items():
        if intent == "resource_search":
            continue
        if any(k in low for k in kws):
            return intent
    raise AssertionError(f"Cannot classify intent for: {text}")


def _assert_role_contract_exists(prompt: str, role: str):
    assert _contains_any(prompt, ROLE_CONTRACT_KEYWORDS[role])


def _assert_soft_referral_style(prompt: str):
    assert not _contains_any(prompt, STIFF_REFUSAL_PHRASES)
    assert _contains_any(prompt, SOFT_REFERRAL_HINTS)


def test_all_agents_include_complete_role_routing_matrix():
    missing: list[tuple[str, str]] = []
    for role in FRONTEND_AGENT_ROLES:
        prompt = _build_prompt(role, "routing matrix contract check")

        try:
            _assert_role_contract_exists(prompt, role)
        except AssertionError:
            missing.append((role, "self_contract"))

        for target in FRONTEND_AGENT_ROLES:
            if not _mentions_role(prompt, target):
                missing.append((role, f"missing_target:{target}"))

    assert not missing, f"Role routing matrix gaps: {missing}"


@pytest.mark.parametrize("intent,expected_target", list(INTENT_TARGET.items()))
def test_request_intent_routes_to_correct_agent(intent: str, expected_target: str):
    req = INTENT_REQUEST[intent]
    assert classify_test_request_intent(req) == intent
    assert INTENT_TARGET[intent] == expected_target


@pytest.mark.parametrize(
    "source_agent,intent,expected_target",
    [
        ("encourager", "resource_search", "resource_finder"),
        ("encourager", "summarization", "summarizer"),
        ("encourager", "concept_explanation", "concept_explainer"),
        ("encourager", "critique", "devil_advocate"),
        ("encourager", "task_planning", "facilitator"),

        ("facilitator", "resource_search", "resource_finder"),
        ("facilitator", "summarization", "summarizer"),
        ("facilitator", "concept_explanation", "concept_explainer"),
        ("facilitator", "critique", "devil_advocate"),
        ("facilitator", "emotional_support", "encourager"),

        ("resource_finder", "task_planning", "facilitator"),
        ("resource_finder", "summarization", "summarizer"),
        ("resource_finder", "concept_explanation", "concept_explainer"),
        ("resource_finder", "critique", "devil_advocate"),
        ("resource_finder", "emotional_support", "encourager"),

        ("summarizer", "resource_search", "resource_finder"),
        ("summarizer", "task_planning", "facilitator"),
        ("summarizer", "concept_explanation", "concept_explainer"),
        ("summarizer", "critique", "devil_advocate"),
        ("summarizer", "emotional_support", "encourager"),

        ("devil_advocate", "summarization", "summarizer"),
        ("devil_advocate", "resource_search", "resource_finder"),
        ("devil_advocate", "task_planning", "facilitator"),
        ("devil_advocate", "concept_explanation", "concept_explainer"),
        ("devil_advocate", "emotional_support", "encourager"),

        ("concept_explainer", "task_planning", "facilitator"),
        ("concept_explainer", "resource_search", "resource_finder"),
        ("concept_explainer", "summarization", "summarizer"),
        ("concept_explainer", "critique", "devil_advocate"),
        ("concept_explainer", "emotional_support", "encourager"),
    ],
)
def test_non_target_agent_refers_to_correct_agent(source_agent: str, intent: str, expected_target: str):
    req = INTENT_REQUEST[intent]
    assert classify_test_request_intent(req) == intent

    prompt = _build_prompt(source_agent, req)
    assert _mentions_role(prompt, expected_target)
    _assert_soft_referral_style(prompt)


@pytest.mark.parametrize(
    "target_agent,intent,forbidden_wrong_target",
    [
        ("facilitator", "task_planning", "resource_finder"),
        ("resource_finder", "resource_search", "facilitator"),
        ("summarizer", "summarization", "resource_finder"),
        ("devil_advocate", "critique", "summarizer"),
        ("concept_explainer", "concept_explanation", "facilitator"),
        ("encourager", "emotional_support", "facilitator"),
    ],
)
def test_target_agent_keeps_in_domain_requests(target_agent: str, intent: str, forbidden_wrong_target: str):
    req = INTENT_REQUEST[intent]
    prompt = _build_prompt(target_agent, req)
    _assert_role_contract_exists(prompt, target_agent)

    if _mentions_role(prompt, forbidden_wrong_target):
        # Matrix can mention other roles globally.
        # For in-domain requests, only fail on explicit wrong mapping patterns.
        low = prompt.lower()
        wrong_map_patterns = [
            f"{intent} -> {forbidden_wrong_target}",
            f"{intent} should be routed to {forbidden_wrong_target}",
            f"{intent} is better handled by {forbidden_wrong_target}",
        ]
        assert not any(p in low for p in wrong_map_patterns)


def test_real_case_encourager_routes_junk_food_resource_request_to_resource_finder():
    req = "Help me find references about junk food."
    assert classify_test_request_intent(req) == "resource_search"

    prompt = _build_prompt("encourager", req)
    low = prompt.lower()

    # matrix can mention facilitator globally; this case must still map resource requests to resource_finder
    assert _mentions_role(prompt, "resource_finder")

    # disallow explicit wrong mapping patterns: resource request -> facilitator
    wrong_patterns = (
        "resource requests should be routed to facilitator",
        "resource_search -> facilitator",
        "references should be handled by facilitator",
        "find references should go to facilitator",
    )
    assert not any(p in low for p in wrong_patterns)
    assert "resource_search -> resource_finder" in low


def test_resource_keywords_take_priority_over_planning_language():
    samples = [
        "Find materials; the scope is large.",
        "Find junk-food evidence, where should I search?",
        "Any related literature and case studies?",
        "Find data sources; there is too much information.",
    ]
    for text in samples:
        assert classify_test_request_intent(text) == "resource_search"

    # Encourage-role contract must prioritize resource_finder for resource requests
    prompt = _build_prompt("encourager", "Find references and evidence; scope is broad.")
    assert _mentions_role(prompt, "resource_finder")


def test_referral_contract_avoids_stiff_refusal_language():
    for role in FRONTEND_AGENT_ROLES:
        prompt = _build_prompt(role, "referral style check")
        assert not _contains_any(prompt, STIFF_REFUSAL_PHRASES)
        assert _contains_any(prompt, SOFT_REFERRAL_HINTS)
