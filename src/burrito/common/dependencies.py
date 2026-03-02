import asyncio
from typing import List, Optional

import httpx
from fastapi import Header, HTTPException, Request

from burrito.common.config import list_from_cfg, settings
from burrito.handlers.generation_handler import GenerationHandler
from burrito.handlers.session_handler import SessionHandler

_session_handler_singleton: Optional[SessionHandler] = None
_generation_handler_singleton: Optional[GenerationHandler] = None
_inference_semaphore_singleton: Optional[asyncio.Semaphore] = None


def get_session_handler() -> SessionHandler:
    global _session_handler_singleton
    if _session_handler_singleton is None:
        _session_handler_singleton = SessionHandler()
    return _session_handler_singleton


def get_generation_handler() -> GenerationHandler:
    global _generation_handler_singleton
    if _generation_handler_singleton is None:
        _generation_handler_singleton = GenerationHandler()
    return _generation_handler_singleton


def get_inference_semaphore() -> asyncio.Semaphore:
    global _inference_semaphore_singleton
    if _inference_semaphore_singleton is None:
        _inference_semaphore_singleton = asyncio.Semaphore(
            settings.MAX_CONCURRENT_INFERENCE_REQUESTS
        )
    return _inference_semaphore_singleton


async def get_backend_models() -> List[dict]:
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            url = f"{settings.BACKEND_BASE_URL}/v1/models"
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Metrics‑specific dependencies
# ---------------------------------------------------------------------------


def require_metrics_token(
    authorization: str | None = Header(None, alias="Authorization"),
):
    """Validate a Bearer token for the /metrics endpoint.

    The token is read from ``settings.METRICS_AUTH_TOKEN``.  If the setting
    is empty the check is skipped, making the endpoint publicly readable.
    """
    token = settings.METRICS_AUTH_TOKEN
    if not token:
        return None
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Missing or malformed Authorization header"
        )
    _, provided = authorization.split(" ", 1)
    if provided != token:
        raise HTTPException(status_code=401, detail="Invalid token")
    return provided


def allow_metrics_ip(request: Request):
    """Allow only IPs listed in ``settings.METRICS_IP_WHITELIST``.

    The environment variable can contain a comma or colon separated list.
    Empty string disables the check.
    """
    whitelist = settings.METRICS_IP_WHITELIST
    if not whitelist:
        return None
    hosts = list_from_cfg(whitelist, "")
    if not request.client or request.client.host not in hosts:
        raise HTTPException(status_code=403, detail="Forbidden IP")
    return None
