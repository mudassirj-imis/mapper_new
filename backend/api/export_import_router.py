"""Export / import of the endpoint registry as JSON, CSV or Postman bundles.

Exports are returned as downloadable blobs (``Content-Disposition: attachment``)
so the frontend can trigger a browser download; imports accept a multipart
``UploadFile`` and return ``{success, imported_endpoints, imported_mappings,
errors}`` — matching the ``exportImportService.js`` contract.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_active_user, get_db
from backend.services.central_auth import CentralUser

# Protected routes receive the centralized identity, not the local ORM user.
User = CentralUser
from backend.services import export_import_service

__all__ = ["router"]

router = APIRouter(tags=["Export / Import"])


def _blob(content: bytes, filename: str, media_type: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/json")
async def export_json(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> Response:
    return _blob(
        await export_import_service.export_json(db),
        "api-mapper-export.json",
        "application/json",
    )


@router.get("/export/csv")
async def export_csv(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> Response:
    return _blob(
        await export_import_service.export_csv(db),
        "api-mapper-export.csv",
        "text/csv",
    )


@router.get("/export/postman")
async def export_postman(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> Response:
    return _blob(
        await export_import_service.export_postman(db),
        "postman-collection.json",
        "application/json",
    )


@router.post("/import/json")
async def import_json(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
):
    return await export_import_service.import_data(db, "json", await file.read())


@router.post("/import/csv")
async def import_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
):
    return await export_import_service.import_data(db, "csv", await file.read())


@router.post("/import/postman")
async def import_postman(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
):
    return await export_import_service.import_data(db, "postman", await file.read())