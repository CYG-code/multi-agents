from uuid import UUID
from typing import Optional
from pydantic import BaseModel, ConfigDict
from app.models.room import RoomStatus


class RoomCreate(BaseModel):
    name: str
    task_id: Optional[UUID] = None


class RoomUpdate(BaseModel):
    status: RoomStatus


class RoomResponse(BaseModel):
    id: UUID
    name: str
    task_id: Optional[UUID]
    created_by: UUID
    status: RoomStatus
    member_count: int = 0

    model_config = ConfigDict(from_attributes=True)
