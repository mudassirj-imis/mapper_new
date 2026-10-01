from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.models import Webhook
from backend.models.webhook import WebhookEvent
from backend.schemas.webhook import WebhookCreate
from backend.services import endpoint_service

logger = logging.getLogger(__name__)

__all__ = [
    "create_webhook",
    "delete_webhook",
    "event_for_result",
    "fire_event",
    "list_webhooks",
    "update_webhook",
]

_TIMEOUT_KINDS = ("upstream_timeout", "local_pool_timeout")


def _fetch_stmt(webhook_id):
    return select(Webhook).where(Webhook.id == webhook_id)


def event_for_result(result: dict[str, Any]) -> str:
    """Map a gateway result dict to a ``WebhookEvent`` value."""
    if result.get("success"):
        return WebhookEvent.CALL_SUCCESS.value
    if result.get("failure_kind") in _TIMEOUT_KINDS:
        return WebhookEvent.CALL_TIMEOUT.value
    return WebhookEvent.CALL_FAILURE.value


async def list_webhooks(db: AsyncSession, endpoint_id=None) -> list[Webhook]:
    """All subscriptions, newest first, optionally scoped to an endpoint."""
    stmt = select(Webhook).order_by(Webhook.created_at.desc())
    if endpoint_id is not None:
        stmt = stmt.where(Webhook.endpoint_id == endpoint_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _ensure_endpoint(db: AsyncSession, endpoint_id) -> None:
    if endpoint_id is not None:
        endpoint = await endpoint_service.get_endpoint(db, endpoint_id)
        if endpoint is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found"
            )


def _event_values(events: Any) -> list[str]:
    """Normalise a ``list[WebhookEvent]``/``list[str]`` to string values."""
    return [getattr(e, "value", e) for e in (events or [])]


async def create_webhook(
    db: AsyncSession, payload: WebhookCreate, created_by: int | None = None
) -> Webhook:
    await _ensure_endpoint(db, payload.endpoint_id)
    row = Webhook(
        endpoint_id=payload.endpoint_id,
        url=str(payload.url),
        events=_event_values(payload.events),
        enabled=payload.enabled,
        created_by=created_by,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def update_webhook(
    db: AsyncSession, webhook_id, data: dict[str, Any]
) -> Webhook | None:
    """Apply a partial update; ``None`` when the row does not exist."""
    result = await db.execute(_fetch_stmt(webhook_id))
    row = result.scalar_one_or_none()
    if row is None:
        return None

    if "endpoint_id" in data:
        await _ensure_endpoint(db, data.get("endpoint_id"))
    if "events" in data and data.get("events") is not None:
        data["events"] = _event_values(data["events"])
    if "url" in data and data.get("url"):
        data["url"] = str(data["url"])

    for field, value in data.items():
        setattr(row, field, value)

    await db.commit()
    await db.refresh(row)
    return row


async def delete_webhook(db: AsyncSession, webhook_id) -> bool:
    result = await db.execute(_fetch_stmt(webhook_id))
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def fire_event(
    db: AsyncSession,
    http_client: httpx.AsyncClient,
    event: str,
    payload: dict[str, Any],
    endpoint_id=None,
) -> None:
    """POST an event to matching (enabled) subscriptions; never raises."""
    try:
        if endpoint_id is not None:
            match = or_(
                Webhook.endpoint_id.is_(None), Webhook.endpoint_id == endpoint_id
            )
        else:
            match = Webhook.endpoint_id.is_(None)
        result = await db.execute(
            select(Webhook).where(Webhook.enabled.is_(True), match)
        )
        targets = [w for w in result.scalars().all() if event in (w.events or [])]
        if not targets:
            return
        body = {
            "event": event,
            "endpoint_id": str(endpoint_id) if endpoint_id else None,
            "payload": payload,
        }
        for target in targets:
            await _deliver(http_client, target.url, body)
    except Exception:
        logger.exception("Webhook dispatch failed for event %s", event)


async def _deliver(
    http_client: httpx.AsyncClient, url: str, body: dict[str, Any]
) -> None:
    """POST ``body`` to ``url`` with a single retry; exceptions are swallowed."""
    timeout = httpx.Timeout(float(settings.WEBHOOK_DELIVERY_TIMEOUT_SECONDS))
    for attempt in range(2):
        try:
            await http_client.post(url, json=body, timeout=timeout)
            return
        except Exception:
            if attempt == 0:
                continue
            logger.exception("Webhook delivery failed to %s", url)
