from fastapi import APIRouter, BackgroundTasks

from app.agents.context_builder import get_recent_messages, get_room_context
from app.agents.llm_client import get_model_routing_status
from app.agents.role_agents import ROLE_AGENTS

router = APIRouter(prefix="/api/debug", tags=["debug"])


@router.post("/trigger-agent")
async def trigger_agent(
    room_id: str,
    role: str = "facilitator",
    background_tasks: BackgroundTasks = None,
):
    agent = ROLE_AGENTS.get(role)
    if agent is None:
        return {"status": "unsupported_role", "room_id": room_id, "role": role}

    context = await get_room_context(room_id)
    history = await get_recent_messages(room_id)

    kwargs = {
        "room_id": room_id,
        "context": context,
        "history": history,
        "trigger_type": "debug",
        "task": {
            "agent_role": role,
            "reason": "调试触发",
            "strategy": "给出一条符合角色设定的自然发言。",
            "priority": 0,
            "trigger_type": "debug",
        },
    }
    if background_tasks is None:
        await agent.generate_and_push(**kwargs)
    else:
        background_tasks.add_task(agent.generate_and_push, **kwargs)

    return {"status": "triggered", "room_id": room_id, "role": role}


@router.get("/model-routing")
async def model_routing_status():
    return await get_model_routing_status()
