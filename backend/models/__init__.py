"""ORM models — importing this package registers every mapper.

Re-exports the models and the shared enums so callers can simply use
``from backend.models import ApiEndpoint, MethodEnum``.
"""

from backend.models.enums import *
from backend.models.enums import (
    CallStatusEnum,
    ContentTypeEnum,
    DataTypeEnum,
    MethodEnum,
    ParamTypeEnum,
    ProtocolEnum,
)
from backend.models.endpoint import ApiEndpoint
from backend.models.parameter import ParameterMapping
from backend.models.log import ApiCallLog
from backend.models.user import User, Role, UserRole
from backend.models.webhook import Webhook, WebhookEvent

__all__ = [
    # Enums (single source of truth, re-exported for convenience)
    "CallStatusEnum",
    "ContentTypeEnum",
    "DataTypeEnum",
    "MethodEnum",
    "ParamTypeEnum",
    "ProtocolEnum",
    "WebhookEvent",
    # ORM models
    "ApiEndpoint",
    "ApiCallLog",
    "ParameterMapping",
    "Role",
    "User",
    "UserRole",
    "Webhook",
]
