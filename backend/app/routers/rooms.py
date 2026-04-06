from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_current_user, require_teacher
from app.models.room_member import RoomMember
from app.models.user import User
from app.schemas.room import RoomCreate, RoomResponse, RoomUpdate
from app.services import room_service
from app.services.message_service import MessageService

router = APIRouter()


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
        raise HTTPException(status_code=404, detail="房间不存在")
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
        raise HTTPException(status_code=404, detail="房间不存在")
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
        raise HTTPException(status_code=404, detail="房间不存在")
    room = await room_service.update_room_status(db, room, data.status)
    return RoomResponse.model_validate(room)


@router.get("/{room_id}/messages")
async def get_messages(
    room_id: UUID,
    before_seq: int | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    room = await room_service.get_room(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    membership = await db.execute(
        select(RoomMember.id).where(
            RoomMember.room_id == room_id,
            RoomMember.user_id == current_user.id,
        )
    )
    if membership.scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="你不是该房间成员")

    return await MessageService.get_history_messages(db, str(room_id), before_seq, limit)
