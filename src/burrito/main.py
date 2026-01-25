from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from contextlib import asynccontextmanager

from burrito.routes.openai_v1 import chat, models, responses


@asynccontextmanager
async def lifespan(app: FastAPI):
    # start singletons / dependencies
    # await browser_tool_singleton.start()

    yield

    # cleanup
    # await browser_tool_singleton.stop()


app = FastAPI(lifespan=lifespan, title="burrito:harness", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (including OPTIONS)
    allow_headers=["*"],  # Allows all headers
)
app.include_router(models.router)
app.include_router(chat.router)
app.include_router(responses.router)
