from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.analysis.scheduler import start_scheduler, stop_scheduler
from app.config import settings
from app.db.redis_client import close_redis, init_redis
from app.routers import auth, rooms, tasks
from app.websocket.handlers import websocket_endpoint


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_redis()
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()
        await close_redis()


app = FastAPI(title="Multi-Agent Learning Collaboration Platform", version="1.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(rooms.router, prefix="/api/rooms", tags=["rooms"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
if settings.debug_enabled:
    try:
        from app.routers import debug

        app.include_router(debug.router)
    except ImportError:
        pass
app.add_api_websocket_route("/ws/{room_id}", websocket_endpoint)
