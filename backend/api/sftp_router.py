from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_active_user, get_db
from backend.services.central_auth import CentralUser

User = CentralUser
from backend.services import sftp_service

__all__ = ["router"]

router = APIRouter(prefix="/sftp", tags=["SFTP"])


class SftpConnectionRequest(BaseModel):
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    endpoint_id: str | None = None


class SftpListRequest(SftpConnectionRequest):
    remote_path: str = "/"


class SftpPreviewRequest(SftpConnectionRequest):
    remote_path: str = "/"
    filename: str


def _payload(model: BaseModel) -> dict:
    return model.model_dump(exclude_none=True)


@router.post("/test-connection")
async def test_connection(
    payload: SftpConnectionRequest,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
):
    try:
        return await sftp_service.test_connection(db, _payload(payload))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.post("/list-files")
async def list_files(
    payload: SftpListRequest,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
):
    try:
        return await sftp_service.list_remote_files(db, _payload(payload))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.post("/preview")
async def preview(
    payload: SftpPreviewRequest,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
):
    try:
        return await sftp_service.list_file_preview(db, _payload(payload))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
