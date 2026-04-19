from __future__ import annotations

import json
import time
import traceback
import uuid
from abc import ABC
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import update

from app.agents.llm_client import stream_completion
from app.agents.settings import get_agent_settings
from app.config import settings
from app.db.redis_client import get_redis_client
from app.db.session import AsyncSessionLocal
from app.models.message import Message, MessageStatus, SenderType
from app.services.message_service import MessageService


class BaseRoleAgent(ABC):
    ROLE: str = "agent"
    ROLE_DISPLAY_NAME: str = "Agent"
    PROMPT_FILE: str = ""
    MAX_TOKENS: int = 512

    def __init__(self):
        if not self.PROMPT_FILE:
            raise ValueError(f"{self.__class__.__name__} must define PROMPT_FILE.")
        prompt_path = Path(__file__).parent / "prompts" / self.PROMPT_FILE
        self._prompt_template = prompt_path.read_text(encoding="utf-8")

    @property
    def model(self) -> str:
        model = get_agent_settings().models.role_agents.model_version
        return model or settings.AGENT_MODEL

    def build_system_prompt(self, context: dict, task: dict | None = None) -> str:
        mention_context = ""
        if task and task.get("trigger_type") == "mention":
            student_name = task.get("student_name") or "某位同学"
            mention_context = (
                f"【附加上下文】用户 {student_name} 刚刚在聊天里 @ 了你。\n"
                "请优先直接回应这次召唤，并保持你的角色风格。"
            )

        return self._prompt_template.format(
            task_description=context.get("task_description", "围绕当前学习任务展开讨论"),
            task_workflow=context.get("task_workflow", "未提供任务流程"),
            members_info=context.get("members_info", "暂无成员信息"),
            current_phase=context.get("current_phase", "阶段未知"),
            intervention_reason=(task or {}).get("reason", "请在当前讨论中给出一次有帮助的发言"),
            strategy=(task or {}).get("strategy", "提出一个可继续讨论的问题"),
            mention_context=mention_context,
        )

    def build_messages(self, history: list[dict]) -> list[dict]:
        formatted = [
            {"role": "user", "content": f"[{msg['display_name']}]: {msg['content']}"}
            for msg in history[-30:]
        ]
        formatted.append(
            {
                "role": "user",
                "content": f"请结合以上讨论，以{self.ROLE_DISPLAY_NAME}身份发言一次。",
            }
        )
        return formatted

    async def generate_and_push(
        self,
        room_id: str,
        context: dict,
        history: list[dict],
        source_message_id: str | None = None,
        trigger_type: str | None = None,
        task: dict | None = None,
    ) -> None:
        message_id = str(uuid.uuid4())

        async with AsyncSessionLocal() as db:
            seq_num = await MessageService.get_next_seq_num(room_id)
            msg = Message(
                id=message_id,
                room_id=room_id,
                seq_num=seq_num,
                sender_type=SenderType.agent,
                agent_role=self.ROLE,
                content="",
                status=MessageStatus.streaming,
            )
            db.add(msg)
            await db.commit()

        await self._broadcast(
            room_id,
            {
                "type": "agent:typing",
                "agent_role": self.ROLE,
                "is_typing": True,
                "source_message_id": source_message_id,
                "trigger_type": trigger_type,
            },
        )

        full_content = ""
        success = True
        db_update_success = False
        error_detail = None

        try:
            system_prompt = self.build_system_prompt(context, task)
            messages = self.build_messages(history)
            async for token in stream_completion(
                system_prompt=system_prompt,
                messages=messages,
                model=self.model,
                max_tokens=self.MAX_TOKENS,
            ):
                full_content += token
                await self._broadcast(
                    room_id,
                    {
                        "type": "agent:stream",
                        "agent_role": self.ROLE,
                        "message_id": message_id,
                        "token": token,
                        "source_message_id": source_message_id,
                        "trigger_type": trigger_type,
                    },
                )
        except Exception as exc:
            print(f"[{self.__class__.__name__}] generation failed: {exc}")
            traceback.print_exc()
            error_detail = str(exc)
            success = False
        finally:
            final_status = MessageStatus.ok if success else MessageStatus.failed
            try:
                async with AsyncSessionLocal() as db:
                    await db.execute(
                        update(Message)
                        .where(Message.id == message_id)
                        .values(content=full_content, status=final_status)
                    )
                    await db.commit()
                    db_update_success = True
            except Exception as exc:
                print(f"[{self.__class__.__name__}] DB update failed: {exc}")
                traceback.print_exc()
                if not error_detail:
                    error_detail = f"DB update failed: {exc}"
                success = False
                final_status = MessageStatus.failed

            if success and db_update_success and full_content.strip():
                redis_client = get_redis_client()
                now_ts = time.time()
                await redis_client.set(f"room:{room_id}:last_msg_time", now_ts)
                await redis_client.sadd("active_rooms", room_id)

            await self._broadcast(
                room_id,
                {
                    "type": "agent:stream_end",
                    "agent_role": self.ROLE,
                    "message_id": message_id,
                    "status": "ok" if success else "failed",
                    "content": full_content,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "source_message_id": source_message_id,
                    "trigger_type": trigger_type,
                    "error": error_detail,
                },
            )

            await self._broadcast(
                room_id,
                {
                    "type": "agent:typing",
                    "agent_role": self.ROLE,
                    "is_typing": False,
                    "source_message_id": source_message_id,
                    "trigger_type": trigger_type,
                },
            )

    async def _broadcast(self, room_id: str, data: dict) -> None:
        redis_client = get_redis_client()
        await redis_client.publish(f"room:{room_id}", json.dumps(data, ensure_ascii=False))


class FacilitatorAgent(BaseRoleAgent):
    ROLE = "facilitator"
    ROLE_DISPLAY_NAME = "主持人"
    PROMPT_FILE = "facilitator.txt"


class DevilAdvocateAgent(BaseRoleAgent):
    ROLE = "devil_advocate"
    ROLE_DISPLAY_NAME = "批判者"
    PROMPT_FILE = "devil_advocate.txt"


class SummarizerAgent(BaseRoleAgent):
    ROLE = "summarizer"
    ROLE_DISPLAY_NAME = "总结者"
    PROMPT_FILE = "summarizer.txt"


class ResourceFinderAgent(BaseRoleAgent):
    ROLE = "resource_finder"
    ROLE_DISPLAY_NAME = "资源检索者"
    PROMPT_FILE = "resource_finder.txt"


class EncouragerAgent(BaseRoleAgent):
    ROLE = "encourager"
    ROLE_DISPLAY_NAME = "鼓励者"
    PROMPT_FILE = "encourager.txt"


ROLE_AGENTS: dict[str, BaseRoleAgent] = {
    "facilitator": FacilitatorAgent(),
    "devil_advocate": DevilAdvocateAgent(),
    "summarizer": SummarizerAgent(),
    "resource_finder": ResourceFinderAgent(),
    "encourager": EncouragerAgent(),
}
