from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from burrito import __version__
from burrito.common.config import list_from_cfg, settings
from burrito.routes import chat, health, messages, metrics, models, responses
from burrito.routes.metrics import (
    request_counter,
    request_latency_error,
    request_latency_success,
)
from burrito.tools.browser.engine import BurritoBrowserEngine


@asynccontextmanager
async def lifespan(app: FastAPI):
    await BurritoBrowserEngine.start()
    yield
    await BurritoBrowserEngine.stop()


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
