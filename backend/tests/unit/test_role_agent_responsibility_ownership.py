from __future__ import annotations

import re

import pytest

from app.agents.role_agents import ROLE_AGENTS


OWNERSHIP_CASES = [
    {
        "agent": "facilitator",
        "request": "We are a bit messy now. What should we do next?",
        "in_domain_keywords": ("facilitator", "workflow", "planning", "next step", "process", "??", "??"),
        "wrong_referral_targets": ("encourager", "summarizer", "resource_finder"),
    },
    {
        "agent": "resource_finder",
        "request": "Do we have evidence for this claim?",
        "in_domain_keywords": ("resource_finder", "evidence", "source", "reference", "??", "??"),
        "wrong_referral_targets": ("facilitator",),
    },
    {
        "agent": "summarizer",
        "request": "Our discussion is scattered. Can you organize it?",
        "in_domain_keywords": ("summarizer", "summary", "consensus", "recap", "??", "??"),
        "wrong_referral_targets": ("facilitator", "resource_finder"),
    },
    {
        "agent": "devil_advocate",
        "request": "Do you think our argument is reliable?",
        "in_domain_keywords": ("devil_advocate", "risk", "counterexample", "challenge", "??", "??"),
        "wrong_referral_targets": ("facilitator", "summarizer"),
    },
    {
        "agent": "concept_explainer",
        "request": "I don't fully understand what this means.",
        "in_domain_keywords": ("concept_explainer", "concept", "term", "theory", "??", "??"),
        "wrong_referral_targets": ("facilitator", "resource_finder"),
    },
    {
        "agent": "encourager",
        "request": "I feel overwhelmed and not confident to speak.",
        "in_domain_keywords": ("encourager", "emotion", "stress", "support", "??", "??"),
        "wrong_referral_targets": ("facilitator",),
    },
]

AMBIGUOUS_IN_DOMAIN_CASES = [
    ("facilitator", "We are a bit messy now. What should we do next?"),
    ("facilitator", "Discussion is stuck. How do we move forward?"),
    ("resource_finder", "Do we have evidence for this point?"),
    ("resource_finder", "Any source that can support this?"),
    ("summarizer", "Can you organize what we have discussed?"),
    ("summarizer", "What have we roughly covered so far?"),
    ("devil_advocate", "Is this claim really reliable?"),
    ("devil_advocate", "Could this plan have hidden problems?"),
    ("concept_explainer", "What does this phrasing mean?"),
    ("concept_explainer", "I don't fully get this theory."),
    ("encourager", "I feel a bit afraid to speak."),
    ("encourager", "I feel I might be holding the team back."),
]

SOFT_REFERRAL_PATTERNS = (
    r"more suitable",
    r"better handled by",
    r"can be handled by",
    r"????",
    r"????",
    r"????",
)


def _build_prompt(agent_role: str, user_request: str) -> str:
    agent = ROLE_AGENTS[agent_role]
    context = {
        "task_description": "Urban heat island collaboration task",
        "task_workflow": "analyze -> explain -> report",
        "members_info": "A/B/C",
        "current_phase": "discussion",
    }
    task = {
        "trigger_type": "mention",
        "reason": f"Student request: {user_request}",
        "strategy": "Keep ownership for in-domain requests.",
        "student_name": "StudentA",
    }
    return agent.build_system_prompt(context=context, task=task)


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(k.lower() in low for k in keywords)


def _refers_out_to_target(prompt: str, target: str) -> bool:
    low = prompt.lower()
    target_low = target.lower()

    soft_markers = (
        "more suitable",
        "better handled by",
        "can be handled by",
        "????",
        "????",
        "????",
    )

    # plain substring-based detection, robust to encoding artifacts
    if target_low not in low:
        return False

    if any(m in low for m in soft_markers):
        return True

    explicit_map_markers = (
        f"-> {target_low}",
        f"to {target_low}",
        f"route to {target_low}",
        f"handled by {target_low}",
    )
    return any(m in low for m in explicit_map_markers)


def _has_ownership_contract(prompt: str, in_domain_keywords: tuple[str, ...]) -> bool:
    return _contains_any(prompt, in_domain_keywords)


@pytest.mark.parametrize("case", OWNERSHIP_CASES, ids=[c["agent"] for c in OWNERSHIP_CASES])
def test_agent_owns_ambiguous_in_domain_request(case: dict):
    prompt = _build_prompt(case["agent"], case["request"])

    assert _has_ownership_contract(prompt, case["in_domain_keywords"])

    for wrong in case["wrong_referral_targets"]:
        assert not _refers_out_to_target(prompt, wrong)


def test_facilitator_owns_ambiguous_next_step_request():
    prompt = _build_prompt("facilitator", "We are a bit messy now. What should we do next?")
    assert _contains_any(prompt, ("facilitator", "workflow", "planning", "process", "??", "??"))
    assert not _refers_out_to_target(prompt, "encourager")
    assert not _refers_out_to_target(prompt, "summarizer")


def test_resource_finder_owns_ambiguous_evidence_request():
    prompt = _build_prompt("resource_finder", "Do we have evidence for this claim?")
    assert _contains_any(prompt, ("resource_finder", "evidence", "source", "reference", "??", "??"))
    assert not _refers_out_to_target(prompt, "facilitator")


def test_summarizer_owns_ambiguous_organize_discussion_request():
    prompt = _build_prompt("summarizer", "Our discussion is scattered. Can you organize it?")
    assert _contains_any(prompt, ("summarizer", "summary", "consensus", "recap", "??", "??"))
    assert not _refers_out_to_target(prompt, "facilitator")
    assert not _refers_out_to_target(prompt, "resource_finder")


def test_devil_advocate_owns_ambiguous_reliability_request():
    prompt = _build_prompt("devil_advocate", "Do you think our argument is reliable?")
    assert _contains_any(prompt, ("devil_advocate", "risk", "counterexample", "challenge", "??", "??"))
    assert not _refers_out_to_target(prompt, "facilitator")
    assert not _refers_out_to_target(prompt, "summarizer")


def test_concept_explainer_owns_ambiguous_understanding_request():
    prompt = _build_prompt("concept_explainer", "I don't fully understand what this means.")
    assert _contains_any(prompt, ("concept_explainer", "concept", "term", "theory", "??", "??"))
    assert not _refers_out_to_target(prompt, "facilitator")
    assert not _refers_out_to_target(prompt, "resource_finder")


def test_encourager_owns_ambiguous_emotional_pressure_request():
    prompt = _build_prompt("encourager", "I feel overwhelmed and not confident to speak.")
    assert _contains_any(prompt, ("encourager", "emotion", "stress", "support", "??", "??"))
    assert not _refers_out_to_target(prompt, "facilitator")


@pytest.mark.parametrize("agent,user_input", AMBIGUOUS_IN_DOMAIN_CASES)
def test_ambiguous_but_in_domain_request_should_not_be_routed_away(agent: str, user_input: str):
    prompt = _build_prompt(agent, user_input)

    ownership_map = {
        "facilitator": ("facilitator", "workflow", "planning", "process", "??", "??"),
        "resource_finder": ("resource_finder", "evidence", "source", "reference", "??", "??"),
        "summarizer": ("summarizer", "summary", "consensus", "recap", "??", "??"),
        "devil_advocate": ("devil_advocate", "risk", "counterexample", "challenge", "??", "??"),
        "concept_explainer": ("concept_explainer", "concept", "term", "theory", "??", "??"),
        "encourager": ("encourager", "emotion", "stress", "support", "??", "??"),
    }
    assert _contains_any(prompt, ownership_map[agent])
