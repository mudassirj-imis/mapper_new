"""Webhook management payloads; destination network checks belong to delivery."""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    TypeAdapter,
    field_validator,
)

from backend.models.webhook import WebhookEvent

_HTTP_URL = TypeAdapter(HttpUrl)


def _validate_destination(value: str) -> str:
    parsed = _HTTP_URL.validate_python(value)
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Webhook URL must not contain credentials")
    if parsed.fragment is not None:
        raise ValueError("Webhook URL must not contain a fragment")
    return str(parsed)


def _unique_events(value: list[WebhookEvent]) -> list[WebhookEvent]:
    if len(set(value)) != len(value):
        raise ValueError("Webhook events must be unique")
    return value


WebhookUrl = Annotated[
    str, Field(max_length=2083), AfterValidator(_validate_destination)
]
WebhookEvents = Annotated[
    list[WebhookEvent],
    Field(min_length=1, max_length=4),
    AfterValidator(_unique_events),
]


class WebhookCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoint_id: UUID | None = None
    url: WebhookUrl
    events: WebhookEvents
    enabled: bool = True


class WebhookUpdate(BaseModel):
    """Omit fields to retain values; only endpoint_id may explicitly be null."""

    model_config = ConfigDict(extra="forbid")

    endpoint_id: UUID | None = None
    url: WebhookUrl | None = None
    events: WebhookEvents | None = None
    enabled: bool | None = None

    @field_validator("url", "events", "enabled", mode="before")
    @classmethod
    def _reject_explicit_null(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("This field may be omitted but cannot be null")
        return value


class WebhookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    endpoint_id: UUID | None
    url: str
    events: list[WebhookEvent]
    enabled: bool
    created_by: int | None
    created_at: datetime
    updated_at: datetime
