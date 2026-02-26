from __future__ import annotations

import uvicorn

from burrito.common.config import settings
from burrito.main import app


def serve():
    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        log_level=settings.LOG_LEVEL,
        access_log=settings.ACCESS_LOG
    )


if __name__ == "__main__":
    serve()
