from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.redis_client import close_redis, init_redis
from app.routers import auth, rooms, tasks
from app.websocket.handlers import websocket_endpoint


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_redis()
    yield
    await close_redis()


app = FastAPI(title="多智能体协作学习平台", version="1.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(rooms.router, prefix="/api/rooms", tags=["房间"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["任务"])
app.add_api_websocket_route("/ws/{room_id}", websocket_endpoint)
