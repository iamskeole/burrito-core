from __future__ import annotations

from fastapi import FastAPI
from contextlib import asynccontextmanager

from burrito.routes.openai_v1 import chat, models, responses
from burrito.common.dependencies import browser_handler_singleton
from burrito.routes import browser_routes


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Start the Browser Process (Playwright)
    await browser_handler_singleton.start()

    yield

    # 2. Cleanup the Browser Process
    await browser_handler_singleton.stop()


app = FastAPI(lifespan=lifespan)


app = FastAPI(title="burrito:harness", version="0.1.0")
app.include_router(models.router)
app.include_router(chat.router)
app.include_router(responses.router)
app.include_router(browser_routes.router)
