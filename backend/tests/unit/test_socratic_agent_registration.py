from pathlib import Path

from app.agents.agent_mode import can_use_agent_role
from app.agents.role_agents import ROLE_AGENTS, SocraticAgent


def test_role_agents_registers_socratic():
    assert "socratic" in ROLE_AGENTS
    assert isinstance(ROLE_AGENTS["socratic"], SocraticAgent)


def test_socratic_agent_metadata():
    agent = ROLE_AGENTS["socratic"]
    assert agent.ROLE == "socratic"
    assert agent.ROLE_DISPLAY_NAME == "苏格拉底智能体"
    assert agent.PROMPT_FILE == "socratic.txt"
    assert agent.SKILL_DIR == "socratic"


def test_single_mode_allows_only_socratic():
    assert can_use_agent_role("single", "socratic") is True
    assert can_use_agent_role("single", "facilitator") is False
    assert can_use_agent_role("single", "devil_advocate") is False
    assert can_use_agent_role("single", "summarizer") is False
    assert can_use_agent_role("single", "resource_finder") is False
    assert can_use_agent_role("single", "encourager") is False
    assert can_use_agent_role("single", "concept_explainer") is False


def test_socratic_prompt_and_skill_files_exist():
    base = Path(__file__).resolve().parents[2] / "app" / "agents"
    assert (base / "prompts" / "socratic.txt").exists()
    assert (base / "skills" / "socratic" / "SKILL.md").exists()


def test_socratic_system_prompt_has_core_constraints():
    agent = ROLE_AGENTS["socratic"]
    prompt = agent.build_system_prompt(
        context={
            "task_description": "协作任务",
            "task_workflow": "分析-比较-结论",
            "members_info": "A/B/C",
            "current_phase": "讨论阶段",
        },
        task={"reason": "学生主动提问", "strategy": "用问题推动思考", "trigger_type": "mention"},
    )

    assert "苏格拉底" in prompt
    assert "不提供最终答案" in prompt or "不直接给答案" in prompt
    assert "不代写" in prompt
    assert "不润色成可提交版本" in prompt or "不润色" in prompt
    assert "每次尽量只提出 1 个核心问题" in prompt or "1 个核心问题" in prompt
