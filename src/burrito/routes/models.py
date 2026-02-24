import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from burrito.common.config import settings

router = APIRouter()


@router.get("/v1/models")
async def v1_responses() -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            base_url = settings.INFERENCE_BACKEND_BASE_URL
            url = f"{base_url}/v1/models"
            response = await client.get(url)
            response.raise_for_status()
            return JSONResponse(
                content=response.json(),
                status_code=response.status_code,
                headers=response.headers,
            )

    except httpx.HTTPStatusError as exc:
        status_code, status_text = exc.response.status_code, exc.response.text
        msg = f"Backend returned status {status_code}: {status_text}"
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
