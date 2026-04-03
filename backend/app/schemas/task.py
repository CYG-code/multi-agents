from uuid import UUID
from typing import Optional, Any
from pydantic import BaseModel, ConfigDict


class TaskCreate(BaseModel):
    title: str
    requirements: Optional[str] = None
    scripts: Optional[Any] = None
    discussion_template: Optional[str] = None


class TaskResponse(BaseModel):
    id: UUID
    title: str
    requirements: Optional[str]
    scripts: Optional[Any]
    discussion_template: Optional[str]
    created_by: UUID

    model_config = ConfigDict(from_attributes=True)
