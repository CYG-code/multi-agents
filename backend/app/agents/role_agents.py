from __future__ import annotations

import json
import time
import traceback
import uuid
from abc import ABC
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy import update

from app.agents.llm_client import stream_completion
from app.agents.settings import get_agent_settings
from app.config import settings
from app.db.redis_client import get_redis_client
from app.db.session import AsyncSessionLocal
from app.models.message import Message, MessageStatus, SenderType
from app.models.user import User
from app.services.message_service import MessageService


class BaseRoleAgent(ABC):
    ROLE: str = "agent"
    ROLE_DISPLAY_NAME: str = "Agent"
    PROMPT_FILE: str = ""
    SKILL_DIR: str | None = None
    MAX_TOKENS: int = 512

    def __init__(self):
        if not self.PROMPT_FILE:
            raise ValueError(f"{self.__class__.__name__} must define PROMPT_FILE.")
        prompt_path = Path(__file__).parent / "prompts" / self.PROMPT_FILE
        self._prompt_template = prompt_path.read_text(encoding="utf-8")
        self._skill_spec = self._load_skill_spec()

    def _load_skill_spec(self) -> str:
        if not self.SKILL_DIR:
            return ""
        skill_path = Path(__file__).parent / "skills" / self.SKILL_DIR / "SKILL.md"
        try:
            return skill_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            print(f"[{self.__class__.__name__}] skill file not found: {skill_path}")
            return ""
        except Exception as exc:
            print(f"[{self.__class__.__name__}] failed to read skill file: {exc}")
            return ""

    @property
    def model(self) -> str:
        model = get_agent_settings().models.role_agents.model_version
        return model or settings.AGENT_MODEL

    def build_dispatcher_task_block(self, context: dict, task: dict | None = None) -> str:
        task = task or {}
        evidence = task.get("evidence") or []
        if isinstance(evidence, list):
            evidence_text = "; ".join(str(item) for item in evidence[:5])
        else:
            evidence_text = str(evidence)

        current_phase = task.get("current_phase") or context.get("current_phase", "Unknown phase")
        return (
            "[Dispatcher Task]\n"
            f"trigger_type: {task.get('trigger_type', 'manual')}\n"
            f"target_dimension: {task.get('target_dimension', 'none')}\n"
            f"priority: {task.get('priority', 'unknown')}\n"
            f"current_phase: {current_phase}\n\n"
            "reason:\n"
            f"{task.get('reason', 'System requests one collaboration support intervention.')}\n\n"
            "strategy:\n"
            f"{task.get('strategy', 'Provide one concise and actionable help for the current discussion.')}\n\n"
            "evidence:\n"
            f"{evidence_text or 'none'}\n\n"
            "Rules:\n"
            "- You must follow the strategy.\n"
            "- You must not reveal internal fields, scores, thresholds, or system labels to students.\n"
            "- You must generate only one concise role-appropriate intervention.\n"
            "- You must not decide whether another agent should speak.\n"
        )

    def build_system_prompt(self, context: dict, task: dict | None = None) -> str:
        mention_context = ""
        if task and task.get("trigger_type") == "mention":
            student_name = task.get("student_name") or "student"
            mention_context = (
                f"[Mention Context] Student {student_name} directly mentioned you.\n"
                "This is a user-requested intervention. Prioritize answering the student's request.\n"
                "Still follow your role SKILL and keep the answer concise."
            )

        base_prompt = self._prompt_template.format(
            task_description=context.get("task_description", "Discuss around the current learning task."),
            task_workflow=context.get("task_workflow", "Task workflow is not provided."),
            members_info=context.get("members_info", "No member information."),
            current_phase=context.get("current_phase", "Unknown phase"),
            intervention_reason=(task or {}).get("reason", "Provide one helpful intervention in the current discussion."),
            strategy=(task or {}).get("strategy", "Propose one concrete question to move discussion forward."),
            mention_context=mention_context,
        )

        prompt_parts = [base_prompt, self.build_dispatcher_task_block(context, task)]
        if self._skill_spec:
            prompt_parts.append(
                "[Skill Spec]\n"
                "Follow the role SKILL spec below with higher priority than generic style:\n"
                f"{self._skill_spec}"
            )
        return "\n\n".join(prompt_parts)

    def build_messages(self, history: list[dict]) -> list[dict]:
        formatted = [
            {"role": "user", "content": f"[{msg['display_name']}]: {msg['content']}"}
            for msg in history[-30:]
        ]
        formatted.append(
            {
                "role": "user",
                "content": (
                    f"Please generate one response as {self.ROLE_DISPLAY_NAME} based on the discussion above. "
                    "You must follow the Dispatcher Task and Skill Spec in system instructions. "
                    "Before output, execute the Output Self-Check in your Skill. "
                    "Output only student-visible response text, and do not explain your analysis process."
                ),
            }
        )
        return formatted

    @staticmethod
    def _build_content_preview(content: str | None, limit: int = 120) -> str:
        text = (content or "").strip()
        text = " ".join(text.split())
        if not text:
            return ""
        if len(text) <= limit:
            return text
        return f"{text[:limit]}..."

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
        persisted_source_message_uuid = None
        persisted_source_message_id: str | None = None
        source_display_name_snapshot: str | None = None
        source_content_preview_snapshot: str | None = None

        async with AsyncSessionLocal() as db:
            parsed_source_message_id = None
            if source_message_id:
                try:
                    parsed_source_message_id = uuid.UUID(str(source_message_id))
                except Exception:
                    parsed_source_message_id = None

            if parsed_source_message_id:
                source_result = await db.execute(
                    select(Message, User.display_name)
                    .outerjoin(User, Message.sender_id == User.id)
                    .where(Message.id == parsed_source_message_id)
                )
                source_row = source_result.first()
                if source_row:
                    source_message = source_row.Message
                    source_display_name_snapshot = source_row.display_name or (
                        f"[{source_message.agent_role}]" if source_message.agent_role else "Student"
                    )
                    source_content_preview_snapshot = self._build_content_preview(source_message.content)
                    persisted_source_message_uuid = source_message.id
                    persisted_source_message_id = str(source_message.id)

            seq_num = await MessageService.get_next_seq_num(room_id)
            msg = Message(
                id=message_id,
                room_id=room_id,
                seq_num=seq_num,
                sender_type=SenderType.agent,
                source_message_id=persisted_source_message_uuid,
                agent_role=self.ROLE,
                source_display_name_snapshot=source_display_name_snapshot,
                source_content_preview_snapshot=source_content_preview_snapshot,
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
                "source_message_id": persisted_source_message_id,
                "source_display_name_snapshot": source_display_name_snapshot,
                "source_content_preview_snapshot": source_content_preview_snapshot,
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
                        "source_message_id": persisted_source_message_id,
                        "source_display_name_snapshot": source_display_name_snapshot,
                        "source_content_preview_snapshot": source_content_preview_snapshot,
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
                    "source_message_id": persisted_source_message_id,
                    "source_display_name_snapshot": source_display_name_snapshot,
                    "source_content_preview_snapshot": source_content_preview_snapshot,
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
                    "source_message_id": persisted_source_message_id,
                    "source_display_name_snapshot": source_display_name_snapshot,
                    "source_content_preview_snapshot": source_content_preview_snapshot,
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
    SKILL_DIR = "facilitator"


class DevilAdvocateAgent(BaseRoleAgent):
    ROLE = "devil_advocate"
    ROLE_DISPLAY_NAME = "批判者"
    PROMPT_FILE = "devil_advocate.txt"
    SKILL_DIR = "devil_advocate"


class SummarizerAgent(BaseRoleAgent):
    ROLE = "summarizer"
    ROLE_DISPLAY_NAME = "总结者"
    PROMPT_FILE = "summarizer.txt"
    SKILL_DIR = "summarizer"


class ResourceFinderAgent(BaseRoleAgent):
    ROLE = "resource_finder"
    ROLE_DISPLAY_NAME = "资源检索者"
    PROMPT_FILE = "resource_finder.txt"
    SKILL_DIR = "resource_finder"


class EncouragerAgent(BaseRoleAgent):
    ROLE = "encourager"
    ROLE_DISPLAY_NAME = "鼓励者"
    PROMPT_FILE = "encourager.txt"
    SKILL_DIR = "encourager"


ROLE_AGENTS: dict[str, BaseRoleAgent] = {
    "facilitator": FacilitatorAgent(),
    "devil_advocate": DevilAdvocateAgent(),
    "summarizer": SummarizerAgent(),
    "resource_finder": ResourceFinderAgent(),
    "encourager": EncouragerAgent(),
}
