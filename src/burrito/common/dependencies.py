import asyncio
from typing import Optional
from burrito.handlers.generation_handler import AdapterGenerationHandler
from burrito.common.config import settings

_inference_semaphore_singleton: Optional[asyncio.Semaphore] = None


def get_generation_handler() -> AdapterGenerationHandler:
    return AdapterGenerationHandler()


def get_inference_semaphore() -> asyncio.Semaphore:
    global _inference_semaphore_singleton
    if _inference_semaphore_singleton is None:
        _inference_semaphore_singleton = asyncio.Semaphore(
            settings.MAX_CONCURRENT_INFERENCE_REQUESTS
        )
    return _inference_semaphore_singleton
