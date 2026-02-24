from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from burrito import __version__
from burrito.common.config import settings
from burrito.routes import chat, messages, models, responses
from burrito.tools.browser.engine import BurritoBrowserEngine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # start singletons / dependencies
    await BurritoBrowserEngine.start()

    yield

    # cleanup
    await BurritoBrowserEngine.stop()


app = FastAPI(lifespan=lifespan, title="burrito:harness", version=__version__)


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


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS.split(","),
    allow_methods=settings.CORS_ALLOWED_METHODS.split(","),
    allow_headers=settings.CORS_ALLOWED_HEADERS.split(","),
    allow_credentials=settings.CORS_ALLOWED_CREDENTIALS,
)
app.include_router(models.router)
app.include_router(chat.router)
app.include_router(responses.router)
app.include_router(messages.router)
