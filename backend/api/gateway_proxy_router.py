"""Legacy dynamic gateway route: ``/{path:path}``.

The old mapper engine exposed a catch-all ``api_route`` that received the
business requests the CRM forwards through ``gatewayhelper`` (e.g.
``GET /getCallByDate2.php?date=...&user=...``), resolved them against
``api_endpoint`` and proxied them upstream. This router reproduces that
contract on top of this app's own :class:`GatewayEngine`, so the exact same
requests are mapped, executed, audited and stored as call logs here.

Registration order matters: ``main.create_app`` includes this router
**last**, so every concrete route (``/``, ``/health``, ``/api/*``) wins the
match and only otherwise-unhandled paths fall through to the gateway.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.core.config import settings
from backend.services.gateway_engine import GatewayEngine
from backend.services.http_client import get_http_client
from backend.services.log_writer import write_call_log

logger = logging.getLogger(__name__)

__all__ = ["router"]

router = APIRouter(tags=["Gateway"])

_METHODS = ("GET", "POST", "PUT", "DELETE", "PATCH")

# Hop-by-hop headers must not be forwarded; a stale Content-Length would
# otherwise contradict the body the engine serialises.
_DROP_HEADERS = frozenset(
    {
        "host",
        "content-length",
        "connection",
        "keep-alive",
        "transfer-encoding",
        "upgrade",
        "expect",
        "te",
        "trailer",
        "proxy-connection",
        "proxy-authorization",
    }
)


async def _request_payload(request: Request) -> dict[str, Any]:
    """Mirror the legacy handler: GET reads the query string, others the JSON."""
    if request.method == "GET":
        return dict(request.query_params)

    try:
        payload = await request.json()
    except Exception:
        return {}

    return payload if isinstance(payload, dict) else {}


@router.api_route("/{path:path}", methods=list(_METHODS))
async def gateway_proxy(
    request: Request,
    path: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    http_client: Any = Depends(get_http_client),
) -> Response:
    """Resolve, proxy and log one dynamically routed business request."""
    target_url = f"/{path}"
    root = settings.APP_ROOT_PATH
    if root and target_url.startswith(f"{root}/"):
        target_url = target_url[len(root) :]

    method = request.method.upper()
    request_data = await _request_payload(request)
    headers = {
        name: value
        for name, value in request.headers.items()
        if name.lower() not in _DROP_HEADERS
    }

    engine = GatewayEngine(db, http_client, timeout=settings.API_TIMEOUT_SECONDS)
    result = await engine.process_request(None, request_data, headers, target_url, method)

    # Only matched endpoints produce an audit row — unresolved probes stay out
    # of api_call_log, exactly like the legacy engine's "log only if endpoint".
    if result.get("endpoint_id") is not None:
        log_data = dict(result)
        log_data["internal_request_body"] = request_data
        background_tasks.add_task(write_call_log, db, log_data)

    status_code = result.get("status_code")
    if status_code is None:
        status_code = 200 if result.get("success") else 500

    logger.info(
        "gateway proxy %s %s -> HTTP %s (endpoint=%s)",
        method,
        target_url,
        status_code,
        result.get("endpoint_id"),
    )

    if status_code == 204:
        return Response(status_code=204)

    content = {key: value for key, value in result.items() if key != "status_code"}
    return JSONResponse(status_code=status_code, content=content)
