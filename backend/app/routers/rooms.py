from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.redis_client import get_redis_client
from app.db.session import get_db
from app.dependencies import get_current_user, require_teacher
from app.exceptions import RoomMemberForbiddenError, RoomNotFoundError
from app.models.room_member import RoomMember
from app.models.user import User, UserRole
from app.schemas.message import MessageHistoryResponse
from app.schemas.room import (
    RoomCreate,
    RoomDeleteRequest,
    RoomResponse,
    RoomTaskBindRequest,
    RoomUpdate,
    TaskScriptConfirmRequest,
)
from app.services import room_service, task_script_service, task_service
from app.services.message_service import MessageService

router = APIRouter()


async def _ensure_room_member(db: AsyncSession, room_id: UUID, user_id: UUID) -> None:
    membership = await db.execute(
        select(RoomMember.id).where(
            RoomMember.room_id == room_id,
            RoomMember.user_id == user_id,
        )
    )
    if membership.scalar_one_or_none() is None:
        raise RoomMemberForbiddenError()


@router.get("", response_model=list[RoomResponse])
async def list_rooms(
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rooms = await room_service.get_rooms(db, status)
    result = []
    for room in rooms:
        count = await room_service.get_member_count(db, room.id)
        resp = RoomResponse.model_validate(room)
        resp.member_count = count
        result.append(resp)
    return result


@router.post("", response_model=RoomResponse, status_code=201)
async def create_room(
    data: RoomCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    room = await room_service.create_room(db, data, current_user.id)
    return RoomResponse.model_validate(room)


@router.get("/{room_id}", response_model=RoomResponse)
async def get_room(
    room_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    room = await room_service.get_room(db, room_id)
    if not room:
        raise RoomNotFoundError()
    count = await room_service.get_member_count(db, room.id)
    resp = RoomResponse.model_validate(room)
    resp.member_count = count
    return resp


@router.post("/{room_id}/join", status_code=200)
async def join_room(
    room_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    room = await room_service.get_room(db, room_id)
    if not room:
        raise RoomNotFoundError()
    await room_service.join_room(db, room_id, current_user.id)
    return {"detail": "已加入房间"}


@router.patch("/{room_id}", response_model=RoomResponse)
async def update_room(
    room_id: UUID,
    data: RoomUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_teacher),
):
    room = await room_service.get_room(db, room_id)
    if not room:
        raise RoomNotFoundError()
    room = await room_service.update_room_status(db, room, data.status)
    count = await room_service.get_member_count(db, room.id)
    resp = RoomResponse.model_validate(room)
    resp.member_count = count
    return resp


@router.patch("/{room_id}/task", response_model=RoomResponse)
async def bind_room_task(
    room_id: UUID,
    data: RoomTaskBindRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_teacher),
):
    room = await room_service.get_room(db, room_id)
    if not room:
        raise RoomNotFoundError()

    task = await task_service.get_task(db, data.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    room = await room_service.bind_room_task(db, room, data.task_id)
    count = await room_service.get_member_count(db, room.id)
    resp = RoomResponse.model_validate(room)
    resp.member_count = count
    return resp


@router.delete("/{room_id}", status_code=200)
async def delete_room(
    room_id: UUID,
    data: RoomDeleteRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_teacher),
):
    room = await room_service.get_room(db, room_id)
    if not room:
        raise RoomNotFoundError()

    if room.name != data.confirm_name.strip():
        raise HTTPException(status_code=400, detail="房间名称确认不匹配")

    await room_service.delete_room(db, room_id)

    try:
        redis_client = get_redis_client()
        room_id_str = str(room_id)
        await redis_client.srem("active_rooms", room_id_str)
        await redis_client.delete(
            f"agent_queue:{room_id_str}",
            f"room:{room_id_str}:last_msg_time",
            f"room:{room_id_str}:start_time",
            f"room:{room_id_str}:agent_lock",
            f"room:{room_id_str}:recent_senders",
            f"trigger_lock:{room_id_str}:silence",
            f"trigger_lock:{room_id_str}:monopoly",
        )
    except RuntimeError:
        pass

    return {"detail": "房间已删除"}


@router.get("/{room_id}/messages", response_model=MessageHistoryResponse)
async def get_messages(
    room_id: UUID,
    before_seq: int | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    room = await room_service.get_room(db, room_id)
    if not room:
        raise RoomNotFoundError()

    await _ensure_room_member(db, room_id, current_user.id)

    return await MessageService.get_history_messages(db, str(room_id), before_seq, limit)


@router.get("/{room_id}/task-script", status_code=200)
async def get_task_script_state(
    room_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    room = await room_service.get_room(db, room_id)
    if not room:
        raise RoomNotFoundError()
    await _ensure_room_member(db, room_id, current_user.id)

    task = await task_service.get_task(db, room.task_id) if room.task_id else None
    return task_script_service.get_task_script_state(task)


@router.post("/{room_id}/task-script/proposals/facilitator", status_code=200)
async def propose_task_script_by_facilitator(
    room_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    room = await room_service.get_room(db, room_id)
    if not room:
        raise RoomNotFoundError()
    await _ensure_room_member(db, room_id, current_user.id)
    return await task_script_service.propose_facilitator_update(db, room, current_user)


@router.post("/{room_id}/task-script/confirm", status_code=200)
async def confirm_task_script_proposal(
    room_id: UUID,
    data: TaskScriptConfirmRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    room = await room_service.get_room(db, room_id)
    if not room:
        raise RoomNotFoundError()
    await _ensure_room_member(db, room_id, current_user.id)
    if current_user.role != UserRole.student:
        raise HTTPException(status_code=403, detail="仅学生可确认流程提案")

    overrides = (data.model_dump(exclude_none=True) if data else {})
    return await task_script_service.confirm_pending_proposal(db, room, current_user, overrides=overrides)
