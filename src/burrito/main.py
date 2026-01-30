from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from contextlib import asynccontextmanager

from burrito.routes.openai_v1 import chat, models, responses
from burrito.common.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # start singletons / dependencies
    # await browser_tool_singleton.start()

    yield

    # cleanup
    # await browser_tool_singleton.stop()


@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    if request.method == "POST":
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > settings.MAX_REQUEST_BODY_SIZE:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=413,
                content={"error": "Request body too large"},
            )
    return await call_next(request)


app = FastAPI(lifespan=lifespan, title="burrito:harness", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,  # Use configurable origins
    allow_methods=["*"],  # Allows all methods (including OPTIONS)
    allow_headers=["*"],  # Allows all headers
    allow_credentials=True,
)
app.include_router(models.router)
app.include_router(chat.router)
app.include_router(responses.router)
