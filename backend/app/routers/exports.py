from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import require_teacher
from app.models.user import User
from app.services import export_service
from app.services.export_service import ExportInclude

router = APIRouter()


class ExportIncludeModel(BaseModel):
    rooms: bool = True
    room_members: bool = True
    messages: bool = True
    agent_tasks: bool = True
    analysis_snapshots: bool = True
    writing_docs: bool = True
    writing_change_logs: bool = True
    room_writing_html: bool = True


class ExportRequest(BaseModel):
    room_id: str | None = None
    room_name_prefix: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    include: ExportIncludeModel = Field(default_factory=ExportIncludeModel)


def _to_include_model(data: ExportIncludeModel) -> ExportInclude:
    return ExportInclude(
        rooms=data.rooms,
        room_members=data.room_members,
        messages=data.messages,
        agent_tasks=data.agent_tasks,
        analysis_snapshots=data.analysis_snapshots,
        writing_docs=data.writing_docs,
        writing_change_logs=data.writing_change_logs,
        room_writing_html=data.room_writing_html,
    )


@router.get("/rooms")
async def list_rooms_for_export(
    room_name_prefix: str | None = Query(default=None),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_teacher),
) -> list[dict[str, Any]]:
    return await export_service.list_export_rooms(
        db,
        room_name_prefix=room_name_prefix,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )


@router.post("/preview")
async def preview_export(
    data: ExportRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_teacher),
) -> dict[str, Any]:
    payload = await export_service.build_export_payload(
        db,
        room_id=data.room_id,
        room_name_prefix=data.room_name_prefix,
        start_time=data.start_time,
        end_time=data.end_time,
        include=_to_include_model(data.include),
    )
    return {
        "matched_room_ids": payload["matched_room_ids"],
        "counts": payload["counts"],
        "estimated_files": payload["estimated_files"],
    }


@router.post("/download")
async def download_export(
    data: ExportRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_teacher),
) -> Response:
    payload = await export_service.build_export_payload(
        db,
        room_id=data.room_id,
        room_name_prefix=data.room_name_prefix,
        start_time=data.start_time,
        end_time=data.end_time,
        include=_to_include_model(data.include),
    )
    zip_bytes = export_service.build_export_zip_bytes(payload)
    filename = f"experiment_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
