from __future__ import annotations

from app.agents.role_agents import ROLE_AGENTS


WHAT_TO_DO_NEXT_REQUEST = "我接下来应该怎么做？"
HELP_ME_BREAK_DOWN_REQUEST = "可以啊帮我拆开吧。"

TASK_GUIDANCE_BANNED_PHRASES = (
    "你可以先",
    "先从",
    "先选",
    "接下来最省力的是",
    "各挑",
    "补一句",
    "拆开",
    "拆解",
    "我可以帮你",
    "如果你愿意，我可以",
)

BREAKDOWN_BANNED_PHRASES = (
    "可以，先拆",
    "学生这一类",
    "便利是什么",
    "不便是什么",
    "各补一句",
    "我可以再帮你",
    "变成可直接讨论的小句子",
)

STIFF_REJECTION_PHRASES = (
    "我不能帮助你",
    "我不能直接回答",
    "这不符合我的角色",
    "禁止",
    "不允许",
)


def _build_prompt_for_user_request(user_request: str) -> str:
    agent = ROLE_AGENTS["encourager"]
    context = {
        "task_description": "围绕城市热岛效应完成三问协作任务。",
        "task_workflow": "先做描述统计，再解释原因，最后提出干预措施。",
        "members_info": "A/B/C 三名学生",
        "current_phase": "writing",
    }
    task = {
        "trigger_type": "mention",
        "reason": f"学生请求：{user_request}",
        "strategy": "只做情绪支持与压力缓冲，不做任务推进，必要时建议请主持人梳理下一步。",
        "student_name": "学生A",
    }
    return agent.build_system_prompt(context=context, task=task)


def _contains_any(text: str, candidates: tuple[str, ...]) -> bool:
    normalized = (text or "").strip()
    return any(item in normalized for item in candidates)


def test_encourager_should_not_provide_task_next_steps():
    prompt = _build_prompt_for_user_request(WHAT_TO_DO_NEXT_REQUEST)
    assert "不负责任务推进，不负责“下一步怎么做”的具体安排" in prompt
    assert "不负责拆解任务、组织论点、生成句子、润色文本" in prompt
    assert "不要说“你可以先……”" in prompt


def test_encourager_should_redirect_task_planning_to_facilitator():
    prompt = _build_prompt_for_user_request(HELP_ME_BREAK_DOWN_REQUEST)
    assert "更适合请主持人来帮你们梳理" in prompt
    assert "向主持人智能体求助" in prompt
    assert "只做情绪支持" in prompt


def test_encourager_should_only_stabilize_emotion_when_student_asks_what_to_do_next():
    sample_reply = (
        "这个问题确实容易卡住，不用急着一下子想完整。"
        "你们已经推进到需要整理思路的阶段了，卡住很正常。"
        "下一步怎么拆更适合请主持人来帮你们梳理；我这边先帮你们稳住节奏，"
        "先别因为卡住就否定前面的努力。"
    )
    assert not _contains_any(sample_reply, TASK_GUIDANCE_BANNED_PHRASES)
    assert not _contains_any(sample_reply, STIFF_REJECTION_PHRASES)
    assert "卡住很正常" in sample_reply
    assert "请主持人" in sample_reply


def test_encourager_should_not_take_over_breakdown_request():
    bad_reply = (
        "可以，先拆学生这一类。你只要先想两点：便利是什么，不便是什么。"
        "然后各补一句，如果你愿意，我可以再帮你把这两句变成可直接讨论的小句子。"
    )
    assert _contains_any(bad_reply, BREAKDOWN_BANNED_PHRASES)
