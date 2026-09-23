"""Lazy bearer-token provider for protected upstream APIs.

Some targets reject calls without an auth token (``Authorization: Bearer
<token>`` or ``X-Api-Token: <token>``). Instead of short-copying a token into
every endpoint row, the gateway can exchange the shared login credentials from
``.env`` for a token at runtime:

    UPSTREAM_AUTH_URL=<login url>
    UPSTREAM_AUTH_EMAIL=<email or username>
    UPSTREAM_AUTH_PASSWORD=<password>

or — for upstreams that expect a fixed token instead of a login — map the host
to its token in ``UPSTREAM_API_TOKENS``:

    UPSTREAM_API_TOKENS=mamtasaath.com=<static api token>

On the first protected call the provider POSTs the credentials to the login
URL, extracts the token from the response JSON, and caches it process-wide.
Subsequent calls reuse the cached token until it nears expiry, then refresh it
in the background of a call (a per-URL ``asyncio.Lock`` prevents a stampede of
concurrent logins when the cache is cold or has just expired).

Some login endpoints (e.g. SSPA/IMIS) require an ENCRYPTED request and return an
ENCRYPTED response. They accept only ``{"encrypted_data": <base64>}``, where the
base64 is AES-256-GCM of ``nonce(12) + ciphertext + tag(16)``. When
``UPSTREAM_AUTH_DECRYPTION_KEY`` is set, the gateway uses that shared symmetric
key both to encrypt the login request and to decrypt the login response before
scanning for the bearer token.

Token acquisition is *best effort*: if the login URL is unset, a login fails, or
encryption/decryption yields no token, the caller keeps whatever behaviour it had
before (the upstream's own 401/TOKEN_MISSING will surface in the audit trail).
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping
from urllib.parse import urlparse

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend.core.config import settings

logger = logging.getLogger(__name__)

__all__ = ["apply_upstream_auth"]

_MAX_DEPTH = 6
_GCM_NONCE_SIZE = 12  # 96-bit nonce, per NIST SP 800-38D recommendation
_GCM_TAG_SIZE = 16


@dataclass(frozen=True, slots=True)
class _CachedToken:
    """A successfully fetched bearer token plus its optional expiry.

    ``expires_at`` is epoch seconds. ``None`` means the server gave no expiry,
    so the token is treated as valid for the lifetime of the process.
    """

    token: str
    expires_at: float | None = None

    def is_valid(self, min_ttl_seconds: float) -> bool:
        if self.expires_at is None:
            return True
        return (self.expires_at - time.time()) > min_ttl_seconds


#: Process-wide cache keyed by login URL (different integrations can coexist and
#: are kept independent). Module-level so the per-request engine instances share
#: the same cached token and lock registry instead of re-authenticating every
#: call.
_CACHE: dict[str, _CachedToken] = {}
_LOCKS: dict[str, asyncio.Lock] = {}


def _configured() -> bool:
    """True when a shared login is fully populated in ``.env``."""
    return bool(
        settings.UPSTREAM_AUTH_URL
        and settings.UPSTREAM_AUTH_EMAIL
        and settings.UPSTREAM_AUTH_PASSWORD
    )


def _login_payload() -> dict[str, str]:
    return {
        settings.UPSTREAM_AUTH_USERNAME_FIELD or "email": settings.UPSTREAM_AUTH_EMAIL,
        settings.UPSTREAM_AUTH_PASSWORD_FIELD or "password": settings.UPSTREAM_AUTH_PASSWORD,
    }


def _lookup_path(data: Any, path: str) -> Any:
    """Traverse a dotted ``a.b.c`` path returning the value or ``None``."""
    current = data
    for part in path.split("."):
        if not isinstance(current, Mapping):
            return None
        if part not in current:
            return None
        current = current[part]
    return current


def _find_value(data: Any, keys: list[str], _depth: int = 0) -> Any:
    """Recursively find the first value whose key (or dotted path) is named."""
    if _depth > _MAX_DEPTH:
        return None
    if isinstance(data, Mapping):
        for key in keys:
            value = _lookup_path(data, key)
            if value is not None:
                return value
        for key in keys:
            if "." in key:
                leaf = key.rsplit(".", 1)[1]
                child = _find_value(data, [leaf], _depth + 1)
                if child is not None:
                    return child
        for value in data.values():
            found = _find_value(value, keys, _depth + 1)
            if found is not None:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _find_value(item, keys, _depth + 1)
            if found is not None:
                return found
    return None


def _parse_expiry(data: Any, keys: list[str]) -> float | None:
    """Return epoch-seconds from ``expires_in``-style values, if present.

    Accepts a plain integer/float (treated as seconds) or an ISO 8601 datetime
    string (parsed as an absolute expiry instant).
    """
    raw = _find_value(data, keys)
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return time.time() + float(raw)
    if isinstance(raw, str):
        text = raw.strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return parsed.timestamp()
        except ValueError:
            return None
    return None


def _process_aes_key(key_str: str) -> bytes:
    """Resolve a 32-byte AES key from base64, hex, or a plain 32-char ASCII string.

    Mirrors ``app/helper/aes.py`` ``_process_key``: try base64, then hex, then
    treat as UTF-8 bytes — each must yield exactly 32 bytes. ``IV`` from the
    server's ``aes.py`` is ignored for GCM, so it is not used here either.
    """
    if "=" in key_str or "+" in key_str or "/" in key_str:
        try:
            key_bytes = base64.b64decode(key_str)
            if len(key_bytes) == 32:
                return key_bytes
        except Exception:
            pass

    if all(c in "0123456789abcdefABCDEF" for c in key_str):
        try:
            key_bytes = bytes.fromhex(key_str)
            if len(key_bytes) == 32:
                return key_bytes
        except ValueError:
            pass

    key_bytes = key_str.encode("utf-8")
    if len(key_bytes) != 32:
        raise ValueError(
            f"Invalid AES key length: expected 32 bytes, got {len(key_bytes)}"
        )
    return key_bytes


def _cipher_key() -> bytes | None:
    """Return the 32-byte AES-GCM key, or ``None`` when not configured."""
    key = settings.UPSTREAM_AUTH_DECRYPTION_KEY
    if not key:
        return None
    return _process_aes_key(key)


def _decrypt_login_payload(data: Any, url: str) -> str | None:
    """Decrypt ``UPSTREAM_AUTH_ENCRYPTED_FIELD`` (base64 AES-256-GCM).

    Matches the server's ``app/helper/aes.py`` layout:
    ``combined = nonce(12) + tag(16) + ciphertext``. Returns the plaintext
    string, or ``None`` when the key is unset/invalid, the field is absent, or
    decryption fails (the token parser then reports whatever it can).
    """
    field = settings.UPSTREAM_AUTH_ENCRYPTED_FIELD or "encrypted_data"
    blob = _find_value(data, [field]) if isinstance(data, Mapping) else None
    if not blob or not isinstance(blob, str):
        return None

    try:
        key = _cipher_key()
    except ValueError as exc:
        logger.warning("Upstream auth login: %s at %s", exc, url)
        return None
    if key is None:
        return None

    try:
        raw = base64.b64decode(blob, validate=True)
    except (ValueError, binascii.Error):
        logger.warning("Upstream auth login: encrypted_data is not valid base64 at %s", url)
        return None
    if len(raw) < _GCM_NONCE_SIZE + _GCM_TAG_SIZE:
        logger.warning("Upstream auth login: encrypted_data too short at %s", url)
        return None

    nonce = raw[:_GCM_NONCE_SIZE]
    tag = raw[_GCM_NONCE_SIZE:_GCM_NONCE_SIZE + _GCM_TAG_SIZE]
    ciphertext = raw[_GCM_NONCE_SIZE + _GCM_TAG_SIZE:]
    try:
        # Server stores tag BEFORE ciphertext; the cryptography AESGCM API wants
        # ciphertext+tag appended, so recombine them before decrypting.
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext + tag, None)
    except Exception as exc:
        logger.warning(
            "Upstream auth login: failed to decrypt encrypted_data at %s: %s", url, exc
        )
        return None
    return plaintext.decode("utf-8", errors="replace")


def _encrypt_login_payload(
    payload: dict[str, str], url: str
) -> dict[str, str] | None:
    """Encrypt the login payload for ``encrypted_data`` (base64 AES-256-GCM).

    The SSPA/IMIS login endpoint accepts ONLY an encrypted request. When a
    cipher key is configured, the plaintext JSON is encrypted with the same key
    used for response decryption and wrapped as
    ``{UPSTREAM_AUTH_ENCRYPTED_FIELD: base64(nonce(12)+tag(16)+ciphertext)}`` —
    matching ``app/helper/aes.py`` ``encrypt``. Returns ``None`` when no key is
    set (so the caller can fall back to a plain payload) or encryption fails.
    """
    field = settings.UPSTREAM_AUTH_ENCRYPTED_FIELD or "encrypted_data"
    try:
        key = _cipher_key()
    except ValueError as exc:
        logger.warning("Upstream auth login: %s at %s", exc, url)
        return None
    if key is None:
        return None

    nonce = os.urandom(_GCM_NONCE_SIZE)
    try:
        aesgcm = AESGCM(key)
        # cryptography returns ciphertext||tag; reorder to the server's tag||ciphertext.
        ct = aesgcm.encrypt(nonce, json.dumps(payload).encode("utf-8"), None)
    except Exception as exc:
        logger.warning(
            "Upstream auth login: failed to encrypt login payload at %s: %s", url, exc
        )
        return None
    ciphertext, tag = ct[:-_GCM_TAG_SIZE], ct[-_GCM_TAG_SIZE:]
    combined = nonce + tag + ciphertext
    return {field: base64.b64encode(combined).decode("ascii")}


async def _login(client: httpx.AsyncClient) -> _CachedToken | None:
    """POST the configured credentials and parse the token from the response.

    The login body may wrap its payload in ``encrypted_data`` (see
    :func:`_decrypt_login_payload`); the decrypted JSON (or bare token string)
    is then scanned for the bearer token. A token is honoured regardless of the
    HTTP status code — some targets return 4xx with a valid encrypted token — so
    only a response that yields no token at all is treated as a failed login.
    """
    url = settings.UPSTREAM_AUTH_URL
    payload = _login_payload()
    content_type = (
        settings.UPSTREAM_AUTH_LOGIN_CONTENT_TYPE or "json"
    ).strip().lower()

    try:
        # SSPA login accepts ONLY an encrypted request. Encrypt the payload and
        # send {encrypted_data: <base64 AES-GCM>} when a cipher key is set;
        # otherwise fall back to a plain body (existing behaviour, still useful
        # for non-encrypted back-ends).
        encrypted = _encrypt_login_payload(payload, url)
        if encrypted is not None:
            response = await client.post(url, json=encrypted)
        elif content_type == "form":
            response = await client.post(url, data=payload)
        else:
            response = await client.post(url, json=payload)
    except (httpx.RequestError, httpx.TimeoutException) as exc:
        logger.warning("Upstream auth login failed (transport) at %s: %s", url, exc)
        return None

    try:
        data = response.json()
    except ValueError:
        logger.warning(
            "Upstream auth login response was not JSON at %s: HTTP %s",
            url,
            response.status_code,
        )
        return None

    decrypted = _decrypt_login_payload(data, url)
    if decrypted is not None:
        try:
            parsed = json.loads(decrypted)
        except ValueError:
            parsed = decrypted
        if isinstance(parsed, Mapping):
            data = parsed
        elif isinstance(parsed, str) and parsed.strip():
            # The decrypted blob was the raw token itself.
            return _CachedToken(token=parsed.strip(), expires_at=None)

    token = _find_value(data, settings.UPSTREAM_AUTH_TOKEN_KEYS)
    if isinstance(token, str) and token.strip():
        return _CachedToken(
            token=token.strip(),
            expires_at=_parse_expiry(data, settings.UPSTREAM_AUTH_EXPIRY_KEYS),
        )

    if response.status_code >= 400:
        logger.warning(
            "Upstream auth login failed at %s: HTTP %s — %s",
            url,
            response.status_code,
            response.text[:500],
        )
    else:
        logger.warning(
            "Upstream auth login succeeded but no token found (looked for %s) at %s",
            settings.UPSTREAM_AUTH_TOKEN_KEYS,
            url,
        )
    return None


async def _cached_token(client: httpx.AsyncClient) -> str | None:
    """Return a valid cached token, refreshing it in place when necessary."""
    if not _configured():
        return None

    url = settings.UPSTREAM_AUTH_URL
    lock = _LOCKS.setdefault(url, asyncio.Lock())

    async with lock:
        cached = _CACHE.get(url)
        if cached is not None and cached.is_valid(
            settings.UPSTREAM_AUTH_MIN_TTL_SECONDS
        ):
            return cached.token
        fresh = await _login(client)
        if fresh is None:
            # Keep serving a just-expired token instead of dropping every call
            # on a transient refresh glitch; the next call retries the login.
            return cached.token if cached is not None else None
        _CACHE[url] = fresh
        return fresh.token


def _header_name() -> str:
    return (settings.UPSTREAM_AUTH_HEADER_NAME or "Authorization").strip()


def _token_value(token: str) -> str:
    prefix = (settings.UPSTREAM_AUTH_TOKEN_PREFIX or "").strip()
    return f"{prefix} {token}".strip() if prefix else token


def _static_token_for(url: str) -> str | None:
    """Return the configured static API token for ``url``'s host, if any.

    Tokens are keyed by host (``UPSTREAM_API_TOKENS``), so a token meant for one
    upstream is never sent to another. A parent-domain entry also matches its
    subdomains (``example.com`` matches ``api.example.com``).
    """
    tokens = settings.UPSTREAM_API_TOKENS or {}
    if not tokens or not url:
        return None
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return None
    if host in tokens:
        return tokens[host]
    for candidate, token in tokens.items():
        if host.endswith("." + candidate):
            return token
    return None


async def apply_upstream_auth(
    header_params: dict[str, str],
    http_client: httpx.AsyncClient,
    upstream_url: str | None = None,
) -> None:
    """Best-effort: inject an auth header into ``header_params``.

    Resolution order:
      1. a host-scoped static token (``UPSTREAM_API_TOKENS``) for the upstream
         URL — for APIs that expect a fixed ``Authorization`` / ``X-Api-Token``;
      2. otherwise the shared login token (``UPSTREAM_AUTH_URL`` + credentials).

    No-op when neither applies, when a token could not be obtained, or when the
    caller already supplied its own ``Authorization`` / ``X-Api-Token`` header
    (explicit caller auth always wins so we never clobber a per-endpoint
    credential).
    """
    header_name = _header_name()
    for existing in header_params:
        if existing.lower() in {"authorization", "x-api-token", header_name.lower()}:
            return

    token = _static_token_for(upstream_url) if upstream_url else None
    if token:
        logger.debug(
            "Injecting static API token header %r for %s", header_name, upstream_url
        )
        header_params[header_name] = _token_value(token)
        return

    if not _configured():
        return

    try:
        token = await _cached_token(http_client)
    except Exception as exc:  # defensive: never break the gateway on auth config
        logger.exception("Upstream auth lookup failed: %s", exc)
        return

    if not token:
        return

    logger.debug("Injecting upstream auth header %r for upstream call", header_name)
    header_params[header_name] = _token_value(token)