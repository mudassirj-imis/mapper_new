"""Webhook subscription CRUD.

``GET/POST /api/webhooks`` and ``PUT/DELETE /api/webhooks/{id}`` manage enabled
subscriptions (global when ``endpoint_id`` is null, or scoped to one endpoint)
that drive the fire-and-forget delivery in :mod:`backend.services.webhook_service`.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_active_user, get_db
from backend.models.user import User
from backend.schemas.common import SuccessResponse
from backend.schemas.webhook import WebhookCreate, WebhookResponse, WebhookUpdate
from backend.services import webhook_service

__all__ = ["router"]

router = APIRouter(tags=["Webhooks"])


@router.get("/webhooks", response_model=list[WebhookResponse])
async def list_webhooks(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> list[WebhookResponse]:
    rows = await webhook_service.list_webhooks(db)
    return [WebhookResponse.model_validate(row) for row in rows]


@router.post(
    "/webhooks",
    response_model=WebhookResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_webhook(
    payload: WebhookCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> WebhookResponse:
    row = await webhook_service.create_webhook(db, payload, created_by=current_user.id)
    return WebhookResponse.model_validate(row)


@router.put("/webhooks/{webhook_id}", response_model=WebhookResponse)
async def update_webhook(
    webhook_id: UUID,
    payload: WebhookUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> WebhookResponse:
    row = await webhook_service.update_webhook(
        db, webhook_id, payload.model_dump(exclude_unset=True)
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found"
        )
    return WebhookResponse.model_validate(row)


@router.delete("/webhooks/{webhook_id}", response_model=SuccessResponse)
async def delete_webhook(
    webhook_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> SuccessResponse:
    deleted = await webhook_service.delete_webhook(db, webhook_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found"
        )
    return SuccessResponse(success=True, message="Webhook deleted")