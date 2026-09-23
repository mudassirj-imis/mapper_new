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

# Fields that accept human-friendly comma-separated strings (in addition to
# JSON lists) when read from the environment. pydantic-settings JSON-decodes
# complex fields directly in the source, before field validators run, so the
# sources are subclassed below to pass raw strings through for these fields.
_RAW_STRING_FIELDS = frozenset({
    "CORS_ORIGINS", "SFTP_PRIVATE_KEY_PATHS",
    "WEBHOOK_ALLOWED_HOSTS", "WEBHOOK_ALLOWED_CIDRS",
    "UPSTREAM_API_TOKENS",
})


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

    # --- Database ------------------------------------------------------------
    # Async DSN consumed by ``backend.db.session`` (asyncpg driver).
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/api_mapper"
    )

    # --- Security --------------------------------------------------------------
    # No defaults on purpose: the app must fail fast when secrets are missing
    # instead of silently running with publicly known values.
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 24
    # AES-256-GCM key for encrypting stored credentials (hex string or
    # passphrase, see ``backend.core.crypto``). Generate with:
    #   python -c "import secrets; print(secrets.token_hex(32))"
    ENCRYPTION_KEY: str

    # --- HTTP -----------------------------------------------------------------
    # ``["*"]`` allows every origin; override per environment with either a
    # JSON list ("[\"https://app.example.com\"]") or a comma-separated string.
    CORS_ORIGINS: list[str] = ["*"]
    API_TIMEOUT_SECONDS: int = 60

    # --- Upstream authentication (shared .env login for protected targets) -------
    # When all three are set, the gateway lazily exchanges these credentials for a
    # bearer token by POSTing to UPSTREAM_AUTH_URL, then injects the token into
    # upstream calls that have no explicit Authorization / X-Api-Token header of
    # their own. Login fields are sent as ``email``/``password`` unless overridden.
    UPSTREAM_AUTH_URL: str | None = None
    UPSTREAM_AUTH_EMAIL: str | None = None
    UPSTREAM_AUTH_PASSWORD: str | None = None
    # Some login endpoints (SSPA/IMIS) require an encrypted request AND return an
    # encrypted response. When UPSTREAM_AUTH_DECRYPTION_KEY is set, the gateway
    # uses it as the shared AES-256-GCM symmetric key to (a) encrypt the login
    # request into UPSTREAM_AUTH_ENCRYPTED_FIELD and (b) decrypt
    # UPSTREAM_AUTH_ENCRYPTED_FIELD from the response. Each value is
    # base64(AES-256-GCM: nonce(12) + tag(16) + ciphertext), exactly matching the
    # server's ``app/helper/aes.py`` (IV is ignored). The key must resolve to
    # exactly 32 bytes: pass the server's AES_SECRET_KEY value, given as base64,
    # hex, or a plain 32-char string (no hashing/derivation is applied).
    UPSTREAM_AUTH_DECRYPTION_KEY: str | None = None
    UPSTREAM_AUTH_ENCRYPTED_FIELD: str = "encrypted_data"
    # Login request shape: field names in the POST body and whether it is sent as
    # JSON (``{"email":..,"password":..}``) or form-encoded.
    UPSTREAM_AUTH_USERNAME_FIELD: str = "email"
    UPSTREAM_AUTH_PASSWORD_FIELD: str = "password"
    UPSTREAM_AUTH_LOGIN_CONTENT_TYPE: str = "json"  # "json" | "form"
    # Header to attach the token to. Default ``Authorization`` sends
    # ``Authorization: Bearer <token>``; set ``X-Api-Token`` (with an empty
    # prefix) to send ``X-Api-Token: <token>`` instead.
    UPSTREAM_AUTH_HEADER_NAME: str = "Authorization"
    UPSTREAM_AUTH_TOKEN_PREFIX: str = "Bearer"  # "" -> send the token as-is
    # Keys (or dotted paths) searched in the login response for the token/expiry.
    # Lists may be overridden in .env as a JSON array string.
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
    # Require at least this many seconds of remaining life before a cached token
    # is considered valid (refresh happens slightly ahead of real expiry).
    UPSTREAM_AUTH_MIN_TTL_SECONDS: int = 60

    # --- Upstream static API tokens (host-scoped) --------------------------------
    # Some upstreams (e.g. mamtasaath.com) do NOT use a login/JWT flow; they expect
    # a fixed API token in Authorization / X-Api-Token. Map the upstream host to its
    # token so the gateway sends the right credential per destination, without
    # affecting other upstreams that use the shared login above.
    #   UPSTREAM_API_TOKENS=mamtasaath.com=<token>,api.other.example=<token>
    # A JSON object string is also accepted: {"mamtasaath.com": "<token>"}
    UPSTREAM_API_TOKENS: dict[str, str] = Field(default_factory=dict)

    # None means use AsyncSSH's default trust files by OMITTING known_hosts.
    # Passing known_hosts=None to AsyncSSH disables verification and is forbidden.
    SFTP_KNOWN_HOSTS_FILE: str | None = None
    SFTP_PRIVATE_KEY_PATHS: list[str] = Field(default_factory=list)
    SFTP_CONNECT_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0)
    SFTP_LOGIN_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0)
    SFTP_OPERATION_TIMEOUT_SECONDS: float = Field(default=20.0, gt=0)
    SFTP_MAX_ENTRIES: int = Field(default=5000, gt=0)
    SFTP_PREVIEW_MAX_BYTES: int = Field(default=1048576, gt=0)
    SFTP_MAX_CONCURRENT: int = Field(default=10, gt=0)
    SFTP_ADMISSION_TIMEOUT_SECONDS: float = Field(default=1.0, gt=0)

    # Empty allowlists do not exempt any destination from private-address checks.
    WEBHOOK_ALLOWED_HOSTS: list[str] = Field(default_factory=list)
    WEBHOOK_ALLOWED_CIDRS: list[str] = Field(default_factory=list)
    WEBHOOK_MAX_JOBS: int = Field(default=100, gt=0)
    WEBHOOK_MAX_CONCURRENT: int = Field(default=10, gt=0)
    WEBHOOK_MAX_CONNECTIONS: int = Field(default=10, gt=0)
    WEBHOOK_MAX_KEEPALIVE_CONNECTIONS: int = Field(default=10, ge=0)
    WEBHOOK_DELIVERY_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0)
    WEBHOOK_RESPONSE_MAX_BYTES: int = Field(default=65536, gt=0)
    WEBHOOK_RETRY_DELAY_SECONDS: float = Field(default=0.25, ge=0)
    WEBHOOK_SHUTDOWN_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0)

    # Each policy owns bounded process-local state; cleanup must preserve guards.
    POLICY_MAX_ENDPOINTS: int = Field(default=10000, gt=0)
    POLICY_IDLE_TTL_SECONDS: float = Field(default=600.0, gt=0)
    POLICY_CLEANUP_INTERVAL_SECONDS: float = Field(default=60.0, gt=0)
    DEDUP_TTL_SECONDS: float = Field(default=5.0, gt=0)
    DEDUP_MAX_ENTRIES: int = Field(default=1000, gt=0)
    DEDUP_MAX_BYTES: int = Field(default=16777216, gt=0)
    DEDUP_MAX_INFLIGHT: int = Field(default=100, gt=0)
    DEDUP_MAX_FOLLOWERS: int = Field(default=1000, gt=0)
    DEDUP_MAX_FOLLOWERS_PER_KEY: int = Field(default=100, gt=0)

    # --- Resilience (rate limiting + circuit breaker) -------------------------
    # Per-endpoint budget fallback when ``api_endpoints.rate_limit_rpm`` is unset.
    RATE_LIMIT_DEFAULT_RPM: int = Field(default=60, ge=0)
    # Coarse global per-client-IP guard for the /api surface (middleware).
    GLOBAL_RATE_LIMIT_RPM: int = Field(default=600, gt=0)
    # Circuit breaker: open after this many failures inside the sliding window…
    CIRCUIT_FAILURE_THRESHOLD: int = Field(default=5, gt=0)
    CIRCUIT_WINDOW_SECONDS: float = Field(default=60.0, gt=0)
    # …and auto-recover (reopen to a single-trial HALF_OPEN) after this timeout.
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
        "CORS_ORIGINS", "SFTP_PRIVATE_KEY_PATHS",
        "WEBHOOK_ALLOWED_HOSTS", "WEBHOOK_ALLOWED_CIDRS", mode="before",
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
