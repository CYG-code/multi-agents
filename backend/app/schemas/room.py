from uuid import UUID
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.models.room import RoomStatus


class RoomCreate(BaseModel):
    name: str
    task_id: Optional[UUID] = None


class RoomUpdate(BaseModel):
    status: RoomStatus


class RoomDeleteRequest(BaseModel):
    confirm_name: str


class RoomTaskBindRequest(BaseModel):
    task_id: UUID


class TaskScriptConfirmRequest(BaseModel):
    current_status: Optional[str] = None
    next_goal: Optional[str] = None
    student_feedback: Optional[str] = None
    proposal_id: Optional[str] = None
    lease_id: Optional[str] = None


class TaskScriptLeaseRequest(BaseModel):
    lease_id: str


class RoomResponse(BaseModel):
    id: UUID
    name: str
    task_id: Optional[UUID]
    created_by: UUID
    status: RoomStatus
    member_count: int = 0
    timer_started_at: Optional[datetime] = None
    timer_deadline_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
