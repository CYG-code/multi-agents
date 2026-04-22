from __future__ import annotations

import json

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.message import Message, MessageStatus
from app.models.room import Room
from app.models.room_member import RoomMember
from app.models.task import Task
from app.models.user import User


def _format_task_workflow(scripts) -> str:
    if scripts is None:
        return "未提供任务流程"
    if isinstance(scripts, dict) and (
        "current_status" in scripts or "next_goal" in scripts or "pending_proposal" in scripts
    ):
        current_status = str(scripts.get("current_status") or "").strip() or "暂无"
        next_goal = str(scripts.get("next_goal") or "").strip() or "暂无"
        pending = scripts.get("pending_proposal")
        pending_text = ""
        if isinstance(pending, dict):
            pending_goal = str(pending.get("next_goal") or "").strip() or "暂无"
            pending_text = f"\n待确认提案下一步：{pending_goal}"
        return f"当前状态：{current_status}\n下一步目标：{next_goal}{pending_text}"
    if isinstance(scripts, str):
        text = scripts.strip()
        return text or "未提供任务流程"
    try:
        return json.dumps(scripts, ensure_ascii=False, indent=2)
    except Exception:
        return str(scripts)


async def get_room_context(room_id: str) -> dict:
    async with AsyncSessionLocal() as db:
        room = await db.get(Room, room_id)
        task = await db.get(Task, room.task_id) if room and room.task_id else None

        result = await db.execute(
            select(User.display_name)
            .join(RoomMember, User.id == RoomMember.user_id)
            .where(RoomMember.room_id == room_id)
        )
        members = [r[0] for r in result.fetchall()]

        task_description = (task.requirements or "").strip() if task else ""
        task_workflow = _format_task_workflow(task.scripts if task else None)

        return {
            "task_description": task_description or "讨论一个社会议题",
            "task_workflow": task_workflow,
            "members_info": "、".join(members),
            "current_phase": "第一阶段：问题分析",
        }


async def get_recent_messages(room_id: str, limit: int = 30) -> list[dict]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Message, User.display_name)
            .outerjoin(User, Message.sender_id == User.id)
            .where(
                Message.room_id == room_id,
                Message.status == MessageStatus.ok,
            )
            .order_by(Message.seq_num.desc())
            .limit(limit)
        )
        rows = result.fetchall()
        rows.reverse()

        return [
            {
                "content": row.Message.content,
                "display_name": row.display_name or f"[{row.Message.agent_role}]",
                "sender_id": str(row.Message.sender_id) if row.Message.sender_id else None,
                "sender_type": row.Message.sender_type.value,
            }
            for row in rows
        ]


async def get_room_members(room_id: str) -> list[dict]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User.id, User.display_name)
            .join(RoomMember, User.id == RoomMember.user_id)
            .where(RoomMember.room_id == room_id)
        )
        return [{"id": str(row.id), "display_name": row.display_name} for row in result.fetchall()]
