import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from burrito.common.dependencies import get_backend_models

router = APIRouter()


@router.get("/v1/models")
async def v1_models(models: list = Depends(get_backend_models)) -> JSONResponse:
    if not models:
        detail = "Backend unreachable or no models set up yet."
        raise HTTPException(status_code=503, detail=detail)
    try:
        return JSONResponse(
            content=models,
            status_code=200,
        )

    except httpx.HTTPStatusError as exc:
        status_code, status_text = exc.response.status_code, exc.response.text
        msg = f"Backend returned status {status_code}: {status_text}."
        error_json = {
            "error": {
                "message": msg,
                "type": "backend_error",
                "status": status_code,
            }
        }
        return JSONResponse(
            error_json,
            status_code=status_code,
            media_type="application/json",
        )

    except httpx.RequestError as exc:
        error_json = {
            "error": {
                "message": f"Connection error: {str(exc)}",
                "type": "connection_error",
                "status": 502,
            }
        }
        return JSONResponse(
            error_json,
            status_code=502,
            media_type="application/json",
        )

    except Exception as exc:
        error_json = {
            "error": {
                "message": f"Internal error: {str(exc)}",
                "type": "internal_error",
                "status": 500,
            }
        }
        return JSONResponse(
            error_json,
            status_code=500,
            media_type="application/json",
        )
