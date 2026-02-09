from __future__ import annotations

import uvicorn
from burrito.main import app
from burrito.common.config import settings


def serve():
    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        log_level=settings.LOG_LEVEL,
    )


if __name__ == "__main__":
    serve()
