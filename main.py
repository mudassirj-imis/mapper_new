"""FastAPI application factory for the API Mapper & Gateway backend.

Run from the project root so the ``backend`` package and the root ``.env``
are picked up:

    uvicorn backend.main:app --reload
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import settings
from backend.services.http_client import create_http_client

# ---------------------------------------------------------------------------
# Routers — all mounted under /api:
#   auth, endpoints_router, parameters_router, gateway_router (live core)
#   health_router, logs_router (Task 8), sftp_router, export_import_router,
#   mock_router, webhook_router (Task 7) — with Task 6 resilience wired into
#   gateway_router (dedup / rate-limit / circuit-breaker) plus the global
#   RateLimitMiddleware below.
#
from backend.api.auth import router as auth_router
from backend.api.endpoints_router import router as endpoints_router
from backend.api.export_import_router import router as export_import_router
from backend.api.gateway_router import router as gateway_router
from backend.api.health_router import router as health_router
from backend.api.logs_router import router as logs_router
from backend.api.mock_router import router as mock_router
from backend.api.parameters_router import router as parameters_router
from backend.api.sftp_router import router as sftp_router
from backend.api.webhook_router import router as webhook_router

from backend.middleware.rate_limit import RateLimitMiddleware
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage process-wide resources.

    A single shared ``httpx.AsyncClient`` (:func:`create_http_client`) is
    created on startup and reused for every upstream call (auth handshakes,
    gateway proxying) to benefit from connection pooling, then closed on
    shutdown.
    """
    app.state.http_client = create_http_client()
    try:
        yield
    finally:
        await app.state.http_client.aclose()


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title="API Mapper & Gateway",
        version="1.0.0",
        lifespan=lifespan,
        # Makes Swagger UI / ReDoc emit prefix-aware links. The proxy serves the
        # /mapper-new prefix, so the generated spec and OAuth2-redirect URLs
        # must carry it too — otherwise the docs page loads but then fetches
        # the origin root's spec, which belongs to a different service.
        root_path=settings.APP_ROOT_PATH,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global per-client-IP guard for the /api surface (coarse safety net on
    # top of the per-endpoint limiter applied inside the gateway router).
    app.add_middleware(RateLimitMiddleware)

    # --- Routers ------------------------------------------------------------
    app.include_router(auth_router, prefix="/api")
    app.include_router(endpoints_router, prefix="/api")
    app.include_router(parameters_router, prefix="/api")
    app.include_router(gateway_router, prefix="/api")
    app.include_router(health_router, prefix="/api")
    app.include_router(logs_router, prefix="/api")
    app.include_router(sftp_router, prefix="/api")
    app.include_router(export_import_router, prefix="/api")
    app.include_router(mock_router, prefix="/api")
    app.include_router(webhook_router, prefix="/api")

    @app.get("/", tags=["meta"])
    async def root() -> dict[str, str]:
        """Basic service metadata."""
        return {
            "name": "API Mapper & Gateway",
            "version": "1.0.0",
            "status": "ok",
        }

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        """Liveness probe."""
        return {"status": "healthy"}

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
