from __future__ import annotations

import asyncio
import time
import warnings
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from burrito import __version__
from burrito.common.config import list_from_cfg, settings
from burrito.common.logger import FastAPILogger
from burrito.common.utils import random_uuid
from burrito.handlers.generation_handler import GenerationHandler
from burrito.handlers.session_handler import SessionHandler
from burrito.routes import chat, health, messages, metrics, models, responses
from burrito.routes.metrics import (
    request_counter,
    request_latency_error,
    request_latency_success,
)
from burrito.tools.browser.engine import BurritoBrowserEngine
from burrito.tools.python.tool import refresh_python_internet_flag

# silence the jupyter_client internals cleanup warnings
# specifically targets the "never awaited" warnings from the jupyter internal bridge
warnings.filterwarnings(
    "ignore",
    category=RuntimeWarning,
    message="coroutine 'KernelClient._async_get_iopub_msg' was never awaited",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # start the browser engine
    await BurritoBrowserEngine.start()

    # initialize singletons and attach to app.state
    # this happens once, sequentially, before the app starts taking requests
    log_id = random_uuid()
    max_requests = settings.MAX_CONCURRENT_INFERENCE_REQUESTS

    inference_client = httpx.AsyncClient(timeout=None)

    app.state.session_handler = SessionHandler(log_id)
    app.state.generation_handler = GenerationHandler(log_id, inference_client)
    app.state.inference_semaphore = asyncio.Semaphore(max_requests)

    await app.state.session_handler.start_maintenance()

    # prime the python tool's online/offline probe before the first request
    await refresh_python_internet_flag()

    logger = FastAPILogger.get_logger(__name__)

    logger.info("Application initialized.")

    yield

    await inference_client.aclose()
    await BurritoBrowserEngine.stop()

    if hasattr(app.state, "session_handler"):
        await app.state.session_handler.shutdown()

    logger.info("Application shutdown: tesources cleaned up.")


app = FastAPI(
    lifespan=lifespan,
    title="burrito",
    version=__version__,
)


@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    if request.method == "POST":
        content_length = request.headers.get("content-length")
        max_length = settings.MAX_REQUEST_BODY_SIZE
        if content_length and int(content_length) > max_length:
            return JSONResponse(
                status_code=413,
                content={"error": "Request body too large"},
            )
    return await call_next(request)


@app.middleware("http")
async def prometheus_metrics_middleware(request: Request, call_next):
    # skip logging metrics for metrics itself
    if request.url.path.startswith("/metrics"):
        return await call_next(request)
    start = time.perf_counter()
    response = await call_next(request)
    latency = time.perf_counter() - start
    m, p, s = request.method, request.url.path, response.status_code
    request_counter.labels(m, p, str(s)).inc()
    if 200 <= s < 300:
        request_latency_success.labels(m, p).observe(latency)
    else:
        request_latency_error.labels(m, p).observe(latency)
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=list_from_cfg(settings.CORS_ALLOWED_ORIGINS, "*"),
    allow_methods=list_from_cfg(settings.CORS_ALLOWED_METHODS, "*"),
    allow_headers=list_from_cfg(settings.CORS_ALLOWED_HEADERS, "*"),
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
)


app.include_router(health.router)
app.include_router(metrics.router)
app.include_router(models.router)
app.include_router(chat.router)
app.include_router(responses.router)
app.include_router(messages.router)
