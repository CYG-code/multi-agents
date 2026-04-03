from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth, rooms, tasks


@asynccontextmanager
async def lifespan(app: FastAPI):
    # P1 阶段：数据库引擎在首次请求时自动连接
    yield
    # 关闭时清理资源


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
