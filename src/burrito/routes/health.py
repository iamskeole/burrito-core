from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from burrito.common.dependencies import get_backend_models

router = APIRouter()


@router.get("/health", status_code=status.HTTP_200_OK)
async def health(models: list = Depends(get_backend_models)):
    if not models:
        detail = "Backend unreachable or no models set up yet."
        raise HTTPException(status_code=503, detail=detail)
    return JSONResponse({"status": "ok"})


@router.get("/live", status_code=status.HTTP_200_OK)
async def live():
    return JSONResponse({"status": "alive"})


@router.get("/ready", status_code=status.HTTP_200_OK)
async def ready():
    return JSONResponse({"ready": True})
