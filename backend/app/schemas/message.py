from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatMessageFrame(BaseModel):
    type: Literal["chat:message"]
    content: str = Field(min_length=1, max_length=2000)
    mentions: list[str] = Field(default_factory=list, max_length=5)


class MessageItem(BaseModel):
    id: str
    room_id: str
    seq_num: int
    sender_type: Literal["student", "agent"]
    sender_id: str | None = None
    source_message_id: str | None = None
    display_name: str | None = None
    source_display_name_snapshot: str | None = None
    agent_role: str | None = None
    source_content_preview_snapshot: str | None = None
    content: str
    status: Literal["streaming", "ok", "failed"]
    created_at: str | None = None

    model_config = ConfigDict(from_attributes=True)


class MessageHistoryResponse(BaseModel):
    messages: list[MessageItem]
    has_more: bool
    oldest_seq: int | None = None
