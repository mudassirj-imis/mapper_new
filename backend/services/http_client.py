"""Shared ``httpx.AsyncClient`` — created once per process in the lifespan.

Every upstream call (gateway proxying, future auth handshakes) reuses this
single client so TCP/TLS connections are pooled instead of rebuilt per
request. The client lives on ``app.state.http_client``; routers obtain it via
the :func:`get_http_client` FastAPI dependency — never by constructing a new
client per request.
"""

import httpx
from fastapi import Request

from backend.core.config import settings

__all__ = ["create_http_client", "get_http_client"]

#: Connection pool sizing: up to 100 sockets, 20 kept alive between calls.
_LIMITS = httpx.Limits(max_connections=100, max_keepalive_connections=20)

#: The connect phase fails fast; the read phase honours API_TIMEOUT_SECONDS.
_CONNECT_TIMEOUT_SECONDS = 10.0


def create_http_client() -> httpx.AsyncClient:
    """Build the process-wide async client (called from the app lifespan).

    Redirects are followed transparently, so a 3xx from an upstream is
    resolved before the gateway ever sees it.
    """
    timeout = httpx.Timeout(
        float(settings.API_TIMEOUT_SECONDS), connect=_CONNECT_TIMEOUT_SECONDS
    )
    return httpx.AsyncClient(
        limits=_LIMITS,
        timeout=timeout,
        follow_redirects=True,
    )


def get_http_client(request: Request) -> httpx.AsyncClient:
    """FastAPI dependency returning the shared client from ``app.state``.

    Raises :class:`RuntimeError` when the lifespan did not run (or the client
    was already shut down) — a server misconfiguration, not a client error.
    """
    client = getattr(request.app.state, "http_client", None)
    if client is None or client.is_closed:
        raise RuntimeError(
            "Shared httpx.AsyncClient is unavailable: the application lifespan "
            "did not start it (or it has already been closed)."
        )
    return client
