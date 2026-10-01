"""Application configuration.

All settings are read from the process environment, falling back to a
``.env`` file located in the current working directory (project root).
"""

import json
from typing import Any

from pydantic import Field, field_validator
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

_RAW_STRING_FIELDS = frozenset(
    {
        "CORS_ORIGINS",
        "SCHEDULER_ALLOWED_HOSTS",
        "SCHEDULER_ALLOWED_CIDRS",
        "UPSTREAM_API_TOKENS",
    }
)


class _RawStringDecodeMixin:
    """Skip JSON decoding for fields handled by our own validators."""

    def decode_complex_value(
        self, field_name: str, field: FieldInfo, value: Any
    ) -> Any:
        if field_name in _RAW_STRING_FIELDS and isinstance(value, str):
            return value
        return super().decode_complex_value(field_name, field, value)


class _EnvSettingsSource(_RawStringDecodeMixin, EnvSettingsSource):
    pass


class _DotEnvSettingsSource(_RawStringDecodeMixin, DotEnvSettingsSource):
    pass


class Settings(BaseSettings):
    """Central configuration for the API Mapper & Gateway backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/api_mapper"
    )

    ENCRYPTION_KEY: str

    #: Server bootstrap (``python main.py`` / PM2). ``reload`` must stay off in
    #: production: the reloader respawns the worker on every source change.
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = Field(default=2528, ge=1, le=65535)
    SERVER_RELOAD: bool = False

    CORS_ORIGINS: list[str] = ["*"]
    API_TIMEOUT_SECONDS: int = 60

    #: Connection pool for the shared ``httpx.AsyncClient``. Sized per
    #: deployment, so it is configuration rather than a module constant.
    HTTP_MAX_CONNECTIONS: int = Field(default=100, gt=0)
    HTTP_MAX_KEEPALIVE_CONNECTIONS: int = Field(default=20, ge=0)
    HTTP_CONNECT_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0)
    # Dedicated SQLite file; never use DATABASE_URL for scheduler state.
    SCHEDULER_DATABASE_PATH: str = "scheduler.db"
    SCHEDULER_TIMEZONE: str = "UTC"
    SCHEDULER_REQUEST_TIMEOUT_SECONDS: float = 30.0
    SCHEDULER_DNS_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0)
    SCHEDULER_ALLOWED_HOSTS: list[str] = Field(default_factory=list)
    SCHEDULER_ALLOWED_CIDRS: list[str] = Field(default_factory=list)
    SCHEDULER_ALLOW_PRIVATE_NETWORKS: bool = False
    SCHEDULER_MAX_CONCURRENT_JOBS: int = Field(default=10, gt=0)
    SCHEDULER_MAX_JOBS: int = Field(default=100, gt=0)
    SCHEDULER_RUN_RETENTION_DAYS: int = Field(default=90, gt=0)
    # Payload guards for the optional request body / captured response body.
    SCHEDULER_MAX_REQUEST_BODY_BYTES: int = Field(default=65536, gt=0)
    SCHEDULER_MAX_RESPONSE_BODY_BYTES: int = Field(default=65536, gt=0)
    SCHEDULER_MAX_HEADERS: int = Field(default=32, gt=0)

    AUDIT_MONGO_ENABLED: bool = True
    #: The legacy gateway (``mapper-engine``) writes a compact MySQL row *and* a
    #: full-detail MongoDB document for every call. The MySQL row carries no
    #: headers, query string or captured log, so the detail blocks in the UI
    #: render empty unless we look the document up. Disable to serve MySQL only.
    AUDIT_MONGO_URI: str = "mongodb://localhost:27017/"
    AUDIT_MONGO_DATABASE: str = "gateway_logs_db"
    AUDIT_MONGO_COLLECTION: str = "api_gateway_logs"
    #: How far either side of a row's ``created_at`` to look for its document.
    #: Both records are written by the same in-process call, so they land within
    #: milliseconds; the slack only absorbs clock jitter and slow inserts.
    AUDIT_MATCH_WINDOW_SECONDS: float = Field(default=5.0, gt=0)
    #: Mongo must never add latency to the log views; fail fast, not slow.
    AUDIT_MONGO_TIMEOUT_MS: int = Field(default=1500, gt=0)

    APP_ROOT_PATH: str = ""

    @field_validator("APP_ROOT_PATH", mode="before")
    @classmethod
    def _normalize_root_path(cls, value: Any) -> str:
        """Normalise to ``""`` or a leading-slash, no-trailing-slash prefix.

        FastAPI concatenates this straight onto ``/openapi.json`` and
        ``/docs/oauth2-redirect``, so ``mapper-new/`` or ``/mapper-new/`` would
        both produce a broken URL.
        """
        if value is None:
            return ""
        text = str(value).strip()
        if not text or text == "/":
            return ""
        return "/" + text.strip("/")

    AUTH_BASE_URL: str
    #: AES-256-GCM key for the central auth envelope. ``central_auth`` falls back
    #: to ``UPSTREAM_AUTH_DECRYPTION_KEY`` when unset, so leaving this blank
    #: silently reuses the upstream key - set it explicitly per environment.
    AUTH_SERVICE_ENCRYPTION_KEY: str | None = None

    UPSTREAM_AUTH_URL: str | None = None
    UPSTREAM_AUTH_EMAIL: str | None = None
    UPSTREAM_AUTH_PASSWORD: str | None = None
    UPSTREAM_AUTH_DECRYPTION_KEY: str | None = None
    UPSTREAM_AUTH_ENCRYPTED_FIELD: str = "encrypted_data"

    UPSTREAM_AUTH_USERNAME_FIELD: str = "email"
    UPSTREAM_AUTH_PASSWORD_FIELD: str = "password"
    UPSTREAM_AUTH_LOGIN_CONTENT_TYPE: str = "json"
    UPSTREAM_AUTH_HEADER_NAME: str = "Authorization"
    UPSTREAM_AUTH_TOKEN_PREFIX: str = "Bearer"

    UPSTREAM_AUTH_TOKEN_KEYS: list[str] = [
        "access_token",
        "token",
        "api_token",
        "id_token",
        "jwt",
        "auth_token",
        "data.access_token",
        "data.token",
        "result.access_token",
        "result.token",
    ]
    UPSTREAM_AUTH_EXPIRY_KEYS: list[str] = [
        "expires_in",
        "expires_in_seconds",
        "token_expires_in",
        "expiry_seconds",
        "access_token_expires_in",
        "access_token_expiry",
        "data.expires_in",
        "result.expires_in",
    ]
    UPSTREAM_AUTH_MIN_TTL_SECONDS: int = 60

    UPSTREAM_API_TOKENS: dict[str, str] = Field(default_factory=dict)

    SFTP_KNOWN_HOSTS_FILE: str | None = None
    SFTP_CONNECT_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0)
    SFTP_LOGIN_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0)
    SFTP_MAX_ENTRIES: int = Field(default=5000, gt=0)
    SFTP_PREVIEW_MAX_BYTES: int = Field(default=1048576, gt=0)
    SFTP_MAX_CONCURRENT: int = Field(default=10, gt=0)

    WEBHOOK_DELIVERY_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0)
    #: Pause before the single delivery retry, so a flapping receiver is not
    #: hammered twice back to back.
    WEBHOOK_RETRY_DELAY_SECONDS: float = Field(default=0.25, ge=0)

    POLICY_MAX_ENDPOINTS: int = Field(default=10000, gt=0)
    DEDUP_TTL_SECONDS: float = Field(default=5.0, gt=0)
    DEDUP_MAX_ENTRIES: int = Field(default=1000, gt=0)

    RATE_LIMIT_DEFAULT_RPM: int = Field(default=60, ge=0)
    GLOBAL_RATE_LIMIT_RPM: int = Field(default=600, gt=0)
    CIRCUIT_FAILURE_THRESHOLD: int = Field(default=5, gt=0)
    CIRCUIT_WINDOW_SECONDS: float = Field(default=60.0, gt=0)
    CIRCUIT_RECOVERY_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Use env/dotenv sources that pass raw strings to our validators."""
        return (
            init_settings,
            _EnvSettingsSource(settings_cls),
            _DotEnvSettingsSource(
                settings_cls,
                env_file=dotenv_settings.env_file,
                env_file_encoding=dotenv_settings.env_file_encoding,
            ),
            file_secret_settings,
        )

    @field_validator(
        "CORS_ORIGINS",
        "SCHEDULER_ALLOWED_HOSTS",
        "SCHEDULER_ALLOWED_CIDRS",
        mode="before",
    )
    @classmethod
    def _parse_cors_origins(cls, value: Any) -> Any:
        """Accept both JSON lists and comma-separated strings from the env."""
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                return json.loads(stripped)
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
        return value

    @field_validator("UPSTREAM_API_TOKENS", mode="before")
    @classmethod
    def _parse_upstream_api_tokens(cls, value: Any) -> Any:
        """Accept a JSON object or ``host=token[,host=token]`` from the env."""
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return {}
            if stripped.startswith("{"):
                return json.loads(stripped)
            tokens: dict[str, str] = {}
            for pair in stripped.split(","):
                if "=" not in pair:
                    continue
                host, token = pair.split("=", 1)
                host = host.strip().lower()
                if host:
                    tokens[host] = token.strip()
            return tokens
        return value


settings = Settings()
