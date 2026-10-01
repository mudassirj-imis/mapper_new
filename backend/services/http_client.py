import httpx
from fastapi import Request

from backend.core.config import settings

__all__ = ["create_http_client", "get_http_client"]


def create_http_client() -> httpx.AsyncClient:

    timeout = httpx.Timeout(
        float(settings.API_TIMEOUT_SECONDS),
        connect=float(settings.HTTP_CONNECT_TIMEOUT_SECONDS),
    )
    limits = httpx.Limits(
        max_connections=int(settings.HTTP_MAX_CONNECTIONS),
        max_keepalive_connections=int(settings.HTTP_MAX_KEEPALIVE_CONNECTIONS),
    )
    return httpx.AsyncClient(
        limits=limits,
        timeout=timeout,
        follow_redirects=True,
    )


def get_http_client(request: Request) -> httpx.AsyncClient:
    """FastAPI dependency returning the shared client from ``app.state``."""
    client = getattr(request.app.state, "http_client", None)
    if client is None or client.is_closed:
        raise RuntimeError(
            "Shared httpx.AsyncClient is unavailable: the application lifespan "
            "did not start it (or it has already been closed)."
        )
    return client
