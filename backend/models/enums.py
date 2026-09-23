"""Single source of truth for enums shared by ORM models and Pydantic schemas.

Every enum subclasses :class:`str` so values serialize to plain JSON strings.
Enum-typed columns in the ORM are stored as ``String`` (never SQLAlchemy
``Enum``) so the database schema stays portable across backends (PostgreSQL
today, MySQL-compatible if ever needed).
"""

import enum

__all__ = [
    "CallStatusEnum",
    "ContentTypeEnum",
    "DataTypeEnum",
    "MethodEnum",
    "ParamTypeEnum",
    "ProtocolEnum",
]


class MethodEnum(str, enum.Enum):
    """HTTP method used for source/target calls."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"


class ContentTypeEnum(str, enum.Enum):
    """Content type of the request body forwarded upstream."""

    JSON = "JSON"
    XML = "XML"
    FORM_URLENCODED = "FORM_URLENCODED"
    MULTIPART = "MULTIPART"
    TEXT = "TEXT"


class DataTypeEnum(str, enum.Enum):
    """Value type applied when transforming a parameter."""

    STRING = "STRING"
    INTEGER = "INTEGER"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"
    FLOAT = "FLOAT"
    JSON = "JSON"


class ParamTypeEnum(str, enum.Enum):
    """Where a mapped parameter travels on the target request."""

    BODY = "BODY"
    HEADER = "HEADER"
    QUERY = "QUERY"


class CallStatusEnum(str, enum.Enum):
    """Outcome recorded for a proxied call."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class ProtocolEnum(str, enum.Enum):
    """Transport used to deliver the mapped payload."""

    HTTP = "HTTP"
    HTTPS = "HTTPS"
    SFTP = "SFTP"
