from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import AsyncSessionLocal
from app.models.message import Message, MessageStatus
from app.models.room import Room
from app.models.room_member import RoomMember
from app.models.task import Task
from app.models.user import User


def _format_task_workflow(scripts: Any) -> str:
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
        return scripts.strip() or "未提供任务流程"
    try:
        return json.dumps(scripts, ensure_ascii=False, indent=2)
    except Exception:
        return str(scripts)


def _derive_phase(elapsed_minutes: int) -> tuple[str, str]:
    if elapsed_minutes < 30:
        return "前期：问题理解与方向澄清", "先明确问题边界、术语定义和可执行的下一步目标"
    if elapsed_minutes < 70:
        return "中期：论证与方案推进", "补齐证据链，推进方案收敛，并确保每位成员有明确分工"
    return "后期：收敛与交付检查", "优先保证可交付性，完成最终整合并检查关键风险"


def _calc_elapsed_minutes(room: Room | None) -> int:
    if room is None or room.timer_started_at is None:
        return 0
    if room.timer_stopped_at is not None:
        end_time = room.timer_stopped_at
    else:
        end_time = datetime.now(timezone.utc)
    started_at = room.timer_started_at
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)
    return max(0, int((end_time - started_at).total_seconds() // 60))


async def get_recent_interventions(room_id: str, limit: int = 5) -> list[dict]:
    """
    Compatible reader for P5 step-5 context.
    If `agent_interventions` table is not ready yet, return [] safely.
    """
    query = text(
        """
        SELECT id, agent_role, trigger_type, reason, strategy, status, created_at
        FROM agent_interventions
        WHERE room_id = :room_id
        ORDER BY created_at DESC
        LIMIT :limit
        """
    )
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(query, {"room_id": str(room_id), "limit": int(limit)})
            rows = result.fetchall()
    except SQLAlchemyError:
        return []
    except Exception:
        return []

    items: list[dict] = []
    for row in rows:
        mapping = getattr(row, "_mapping", row)
        created_at = mapping["created_at"]
        items.append(
            {
                "id": str(mapping["id"]),
                "agent_role": mapping["agent_role"],
                "trigger_type": mapping["trigger_type"],
                "reason": mapping["reason"],
                "strategy": mapping["strategy"],
                "status": str(mapping["status"]) if mapping["status"] is not None else None,
                "created_at": created_at.isoformat() if created_at is not None else None,
            }
        )
    return items


async def get_room_context(room_id: str) -> dict:
    async with AsyncSessionLocal() as db:
        room = await db.get(Room, room_id)
        task = await db.get(Task, room.task_id) if room and room.task_id else None
    members = await get_room_members(room_id)

    elapsed_minutes = _calc_elapsed_minutes(room)
    current_phase, phase_goal = _derive_phase(elapsed_minutes)
    task_description = (task.requirements or "").strip() if task else ""
    task_workflow = _format_task_workflow(task.scripts if task else None)
    recent_interventions = await get_recent_interventions(room_id, limit=5)

    return {
        "room_id": str(room.id) if room else str(room_id),
        "task_description": task_description or "讨论一个社会议题并形成可执行结论",
        "task_workflow": task_workflow,
        "current_phase": current_phase,
        "phase_goal": phase_goal,
        "members": members,
        "members_info": "、".join(m["display_name"] for m in members) if members else "暂无成员信息",
        "elapsed_minutes": elapsed_minutes,
        "recent_interventions": recent_interventions,
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
            "id": str(row.Message.id),
            "seq_num": row.Message.seq_num,
            "content": row.Message.content,
            "display_name": row.display_name or f"[{row.Message.agent_role}]",
            "sender_id": str(row.Message.sender_id) if row.Message.sender_id else None,
            "sender_type": row.Message.sender_type.value,
            "agent_role": row.Message.agent_role,
            "created_at": row.Message.created_at.isoformat() if row.Message.created_at else None,
        }
        for row in rows
    ]


async def get_room_members(room_id: str) -> list[dict]:
    async with AsyncSessionLocal() as db:
        room = await db.get(Room, room_id)
        locked_member_ids = []
        room_locked_member_ids = getattr(room, "locked_member_ids", None) if room else None
        if isinstance(room_locked_member_ids, list):
            locked_member_ids = [str(uid) for uid in room_locked_member_ids if uid]

        if locked_member_ids:
            result = await db.execute(
                select(User.id, User.display_name).where(User.id.in_(locked_member_ids))
            )
            members = [{"id": str(row.id), "display_name": row.display_name} for row in result.fetchall()]
            order = {uid: idx for idx, uid in enumerate(locked_member_ids)}
            members.sort(key=lambda item: order.get(item["id"], 10**9))
            return members

        result = await db.execute(
            select(User.id, User.display_name)
            .join(RoomMember, User.id == RoomMember.user_id)
            .where(RoomMember.room_id == room_id)
        )
        return [{"id": str(row.id), "display_name": row.display_name} for row in result.fetchall()]
