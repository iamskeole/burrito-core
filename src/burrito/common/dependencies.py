import asyncio
from typing import Optional, List

import httpx

from burrito.common.config import settings
from burrito.handlers.generation_handler import AdapterGenerationHandler
from burrito.handlers.session_handler import AdapterSessionHandler

_session_handler_singleton: Optional[AdapterSessionHandler] = None
_generation_handler_singleton: Optional[AdapterGenerationHandler] = None
_inference_semaphore_singleton: Optional[asyncio.Semaphore] = None


def get_session_handler() -> AdapterSessionHandler:
    global _session_handler_singleton
    if _session_handler_singleton is None:
        _session_handler_singleton = AdapterSessionHandler()
    return _session_handler_singleton


def get_generation_handler() -> AdapterGenerationHandler:
    global _generation_handler_singleton
    if _generation_handler_singleton is None:
        _generation_handler_singleton = AdapterGenerationHandler()
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
