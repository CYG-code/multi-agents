from fastapi import APIRouter, BackgroundTasks

from app.agents.context_builder import get_recent_messages, get_room_context
from app.agents.role_agents import FacilitatorAgent

router = APIRouter(prefix="/api/debug", tags=["debug"])
facilitator = FacilitatorAgent()


@router.post("/trigger-agent")
async def trigger_agent(
    room_id: str,
    background_tasks: BackgroundTasks,
):
    context = await get_room_context(room_id)
    history = await get_recent_messages(room_id)
    background_tasks.add_task(
        facilitator.generate_and_push,
        room_id=room_id,
        context=context,
        history=history,
    )
    return {"status": "triggered", "room_id": room_id, "role": "facilitator"}
