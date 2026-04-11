import json
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import update

from app.agents.llm_client import stream_completion
from app.config import settings
from app.db.redis_client import get_redis_client
from app.db.session import AsyncSessionLocal
from app.models.message import Message, MessageStatus, SenderType
from app.services.message_service import MessageService


class FacilitatorAgent:
    ROLE = "facilitator"
    ROLE_DISPLAY_NAME = "Facilitator"

    def __init__(self):
        self.model = settings.AGENT_MODEL
        prompt_path = Path(__file__).parent / "prompts" / "facilitator.txt"
        self._prompt_template = prompt_path.read_text(encoding="utf-8")

    def build_system_prompt(self, context: dict) -> str:
        return self._prompt_template.format(
            task_description=context.get("task_description", "Group discussion"),
            members_info=context.get("members_info", ""),
            current_phase=context.get("current_phase", "Phase 1: problem analysis"),
        )

    def build_messages(self, history: list[dict]) -> list[dict]:
        history_lines = [f"[{msg['display_name']}]: {msg['content']}" for msg in history[-30:]]
        merged_context = "\n".join(history_lines)

        return [
            {
                "role": "user",
                "content": (
                    "Below is the recent group discussion history. "
                    "Please speak as the facilitator and provide one natural, concise message.\n\n"
                    f"{merged_context}"
                ),
            }
        ]

    async def generate_and_push(
        self,
        room_id: str,
        context: dict,
        history: list[dict],
        source_message_id: str | None = None,
        trigger_type: str | None = None,
    ):
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
            },
        )

        full_content = ""
        success = True
        db_update_success = False
        error_detail = None

        try:
            system_prompt = self.build_system_prompt(context)
            messages = self.build_messages(history)
            async for token in stream_completion(
                system_prompt=system_prompt,
                messages=messages,
                model=self.model,
                max_tokens=512,
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
                    },
                )
        except Exception as exc:
            print(f"[FacilitatorAgent] generation failed: {exc}")
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
                print(f"[FacilitatorAgent] DB update failed: {exc}")
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
                    "created_at": datetime.utcnow().isoformat(),
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
                },
            )

    async def _broadcast(self, room_id: str, data: dict):
        redis_client = get_redis_client()
        await redis_client.publish(f"room:{room_id}", json.dumps(data, ensure_ascii=False))
