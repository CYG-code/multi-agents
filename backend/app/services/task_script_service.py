from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from app.agents.context_builder import get_recent_messages, get_room_context
from app.agents.llm_client import stream_completion
from app.agents.settings import get_agent_settings
from app.models.room import Room
from app.models.user import User
from app.services import task_service


def _to_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    try:
        return json.dumps(value, ensure_ascii=False).strip()
    except Exception:
        return str(value).strip()


def _normalize_scripts(raw_scripts) -> dict:
    if isinstance(raw_scripts, dict):
        history = raw_scripts.get("history")
        pending = raw_scripts.get("pending_proposal")
        return {
            "current_status": _to_text(raw_scripts.get("current_status")),
            "next_goal": _to_text(raw_scripts.get("next_goal")),
            "history": history if isinstance(history, list) else [],
            "pending_proposal": pending if isinstance(pending, dict) else None,
        }

    if isinstance(raw_scripts, str):
        return {
            "current_status": raw_scripts.strip(),
            "next_goal": "",
            "history": [],
            "pending_proposal": None,
        }

    return {
        "current_status": "",
        "next_goal": "",
        "history": [],
        "pending_proposal": None,
    }


def get_task_script_state(task) -> dict:
    state = _normalize_scripts(task.scripts if task else None)
    return {
        "task_id": str(task.id) if task else None,
        "current_status": state["current_status"],
        "next_goal": state["next_goal"],
        "pending_proposal": state["pending_proposal"],
        "history": state["history"],
    }


def _extract_json_object(raw_text: str) -> dict:
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("empty model output")

    if "```" in text:
        parts = text.split("```")
        for block in parts:
            block = block.strip()
            if block.startswith("json"):
                block = block[4:].strip()
            if block.startswith("{") and block.endswith("}"):
                return json.loads(block)

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])

    raise ValueError("cannot parse json object from model output")


async def _generate_facilitator_proposal(room_id: str) -> dict:
    context = await get_room_context(room_id)
    history = await get_recent_messages(room_id, limit=30)

    system_prompt = (
        "你是学习小组主持智能体，现在要为“任务流程面板”产出一次更新提案。"
        "请严格输出 JSON，不要输出任何额外文本。"
        'JSON 结构必须为 {"current_status": "...", "next_goal": "...", "change_reason": "..."}。'
        "要求：current_status 和 next_goal 要具体、可执行、50字内；change_reason 解释为什么现在要这样改。"
    )
    messages = [
        {"role": "user", "content": f"任务描述：{context.get('task_description', '')}"},
        {"role": "user", "content": f"任务流程：{context.get('task_workflow', '')}"},
        {"role": "user", "content": f"成员信息：{context.get('members_info', '')}"},
    ]
    for msg in history[-20:]:
        messages.append({"role": "user", "content": f"[{msg['display_name']}]: {msg['content']}"})
    messages.append(
        {
            "role": "user",
            "content": "请根据以上讨论输出任务流程面板提案 JSON。",
        }
    )

    model = get_agent_settings().models.role_agents.model_version
    text = ""
    async for token in stream_completion(
        system_prompt=system_prompt,
        messages=messages,
        model=model,
        max_tokens=300,
    ):
        text += token

    payload = _extract_json_object(text)
    current_status = _to_text(payload.get("current_status"))
    next_goal = _to_text(payload.get("next_goal"))
    change_reason = _to_text(payload.get("change_reason"))
    if not current_status or not next_goal:
        raise ValueError("facilitator proposal missing required fields")
    return {
        "current_status": current_status,
        "next_goal": next_goal,
        "change_reason": change_reason,
    }


async def propose_facilitator_update(db, room: Room, current_user: User) -> dict:
    if not room.task_id:
        raise HTTPException(status_code=400, detail="当前房间未绑定任务，无法生成流程提案")
    task = await task_service.get_task(db, room.task_id)
    if task is None:
        raise HTTPException(status_code=400, detail="当前房间未绑定任务，无法生成流程提案")

    base = _normalize_scripts(task.scripts)
    generated = await _generate_facilitator_proposal(str(room.id))

    proposal = {
        "id": str(uuid.uuid4()),
        "agent_role": "facilitator",
        "proposed_at": datetime.now(timezone.utc).isoformat(),
        "requested_by": str(current_user.id),
        "current_status": generated["current_status"],
        "next_goal": generated["next_goal"],
        "change_reason": generated["change_reason"],
    }
    task.scripts = {
        "current_status": base["current_status"],
        "next_goal": base["next_goal"],
        "history": base["history"],
        "pending_proposal": proposal,
    }
    await db.commit()
    await db.refresh(task)
    return get_task_script_state(task)


async def confirm_pending_proposal(db, room: Room, current_user: User, overrides: dict | None = None) -> dict:
    if not room.task_id:
        raise HTTPException(status_code=400, detail="当前房间未绑定任务")
    task = await task_service.get_task(db, room.task_id)
    if task is None:
        raise HTTPException(status_code=400, detail="当前房间未绑定任务")

    base = _normalize_scripts(task.scripts)
    pending = base["pending_proposal"]
    if not pending:
        raise HTTPException(status_code=400, detail="当前没有待确认提案")
    overrides = overrides or {}

    final_current_status = _to_text(overrides.get("current_status"))
    if not final_current_status:
        final_current_status = _to_text(pending.get("current_status"))
    final_next_goal = _to_text(overrides.get("next_goal"))
    if not final_next_goal:
        final_next_goal = _to_text(pending.get("next_goal"))
    student_feedback = _to_text(overrides.get("student_feedback"))

    if not final_current_status or not final_next_goal:
        raise HTTPException(status_code=400, detail="确认内容不能为空，请补充后再确认")

    original_current_status = _to_text(pending.get("current_status"))
    original_next_goal = _to_text(pending.get("next_goal"))
    student_adjusted = (
        final_current_status != original_current_status or final_next_goal != original_next_goal
    )

    now_iso = datetime.now(timezone.utc).isoformat()
    new_history = list(base["history"])
    new_history.append(
        {
            "id": pending.get("id") or str(uuid.uuid4()),
            "agent_role": pending.get("agent_role") or "facilitator",
            "confirmed_at": now_iso,
            "confirmed_by": str(current_user.id),
            "current_status": final_current_status,
            "next_goal": final_next_goal,
            "change_reason": _to_text(pending.get("change_reason")),
            "facilitator_suggested_current_status": original_current_status,
            "facilitator_suggested_next_goal": original_next_goal,
            "student_adjusted": student_adjusted,
            "student_feedback": student_feedback,
        }
    )

    task.scripts = {
        "current_status": final_current_status,
        "next_goal": final_next_goal,
        "history": new_history[-100:],
        "pending_proposal": None,
    }
    await db.commit()
    await db.refresh(task)
    return get_task_script_state(task)
